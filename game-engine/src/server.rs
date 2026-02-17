//! gRPC server implementation for GameEngineService.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;
use tonic::{Request, Response, Status};

use crate::engine::arena::run_arena;
use crate::engine::bot_strategy::{BotStrategy, MctsStrategy, RandomStrategy};
use crate::engine::mcts::{mcts_search, MctsParams};
use crate::engine::models;
use crate::engine::plugin::{GamePlugin, TypedGamePlugin};
use crate::games::carcassonne::evaluator::{
    make_carcassonne_eval, AGGRESSIVE_WEIGHTS, CONSERVATIVE_WEIGHTS, DEFAULT_WEIGHTS,
    FIELD_HEAVY_WEIGHTS,
};
use crate::games::carcassonne::plugin::CarcassonnePlugin;
use crate::games::carcassonne::types::CarcassonneState;
use crate::games::tictactoe::TicTacToePlugin;
use crate::games::GameRegistry;

pub mod proto {
    tonic::include_proto!("meeple.game_engine.v1");
}

use proto::game_engine_service_server::GameEngineService;
use proto::*;

/// The gRPC service implementation.
pub struct GameEngineServer {
    registry: Arc<GameRegistry>,
}

impl GameEngineServer {
    pub fn new(registry: GameRegistry) -> Self {
        Self {
            registry: Arc::new(registry),
        }
    }

    fn get_plugin(&self, game_id: &str) -> Result<&dyn GamePlugin, Status> {
        self.registry
            .get(game_id)
            .ok_or_else(|| Status::not_found(format!("unknown game_id: {}", game_id)))
    }
}

// --- Conversion helpers: protobuf <-> engine types ---

fn proto_to_player(p: &Player) -> models::Player {
    models::Player {
        player_id: p.player_id.clone(),
        display_name: p.display_name.clone(),
        seat_index: p.seat_index,
        is_bot: p.is_bot,
        bot_id: if p.bot_id.is_empty() {
            None
        } else {
            Some(p.bot_id.clone())
        },
    }
}

fn proto_to_players(players: &[Player]) -> Vec<models::Player> {
    players.iter().map(proto_to_player).collect()
}

fn proto_to_config(config: &GameConfig) -> models::GameConfig {
    let options = if config.options.is_empty() {
        serde_json::json!({})
    } else {
        let map: serde_json::Map<String, serde_json::Value> = config
            .options
            .iter()
            .map(|(k, v)| {
                // Try parsing the value as JSON, fall back to string
                let val = serde_json::from_str(v).unwrap_or(serde_json::Value::String(v.clone()));
                (k.clone(), val)
            })
            .collect();
        serde_json::Value::Object(map)
    };
    models::GameConfig {
        options,
        random_seed: config.random_seed.map(|s| s as u64),
    }
}

fn proto_to_phase(phase: &Phase) -> models::Phase {
    let expected_actions = phase
        .expected_actions
        .iter()
        .map(|ea| models::ExpectedAction {
            player_id: ea.player_id.clone().unwrap_or_default(),
            action_type: ea.action_type.clone(),
            constraints: HashMap::new(),
            timeout_ms: None,
        })
        .collect();

    let concurrent_mode = match phase.concurrent_mode.as_str() {
        "commit_reveal" => Some(models::ConcurrentMode::CommitReveal),
        "time_window" => Some(models::ConcurrentMode::TimeWindow),
        _ => None,
    };

    let metadata = if phase.metadata.is_empty() {
        serde_json::json!({})
    } else {
        let map: serde_json::Map<String, serde_json::Value> = phase
            .metadata
            .iter()
            .map(|(k, v)| {
                let val = serde_json::from_str(v).unwrap_or(serde_json::Value::String(v.clone()));
                (k.clone(), val)
            })
            .collect();
        serde_json::Value::Object(map)
    };

    models::Phase {
        name: phase.name.clone(),
        concurrent_mode,
        expected_actions,
        auto_resolve: phase.auto_resolve,
        metadata,
    }
}

fn proto_to_action(action: &Action) -> models::Action {
    let payload = if action.payload_json.is_empty() {
        serde_json::json!({})
    } else {
        serde_json::from_slice(&action.payload_json).unwrap_or(serde_json::json!({}))
    };
    models::Action {
        action_type: action.action_type.clone(),
        player_id: action.player_id.clone(),
        payload,
    }
}

fn game_data_from_bytes(bytes: &[u8]) -> Result<serde_json::Value, Status> {
    serde_json::from_slice(bytes)
        .map_err(|e| Status::invalid_argument(format!("invalid game_data JSON: {}", e)))
}

fn game_data_to_bytes(value: &serde_json::Value) -> Vec<u8> {
    serde_json::to_vec(value).unwrap_or_default()
}

// Engine -> proto conversions

fn phase_to_proto(phase: &models::Phase) -> Phase {
    let expected_actions = phase
        .expected_actions
        .iter()
        .map(|ea| ExpectedAction {
            player_id: if ea.player_id.is_empty() {
                None
            } else {
                Some(ea.player_id.clone())
            },
            action_type: ea.action_type.clone(),
        })
        .collect();

    let concurrent_mode = match &phase.concurrent_mode {
        Some(models::ConcurrentMode::CommitReveal) => "commit_reveal".into(),
        Some(models::ConcurrentMode::TimeWindow) => "time_window".into(),
        _ => "sequential".into(),
    };

    let metadata = if let Some(obj) = phase.metadata.as_object() {
        obj.iter()
            .map(|(k, v)| (k.clone(), serde_json::to_string(v).unwrap_or_default()))
            .collect()
    } else {
        HashMap::new()
    };

    Phase {
        name: phase.name.clone(),
        concurrent_mode,
        expected_actions,
        auto_resolve: phase.auto_resolve,
        metadata,
    }
}

fn event_to_proto(event: &models::Event) -> Event {
    Event {
        event_type: event.event_type.clone(),
        player_id: event.player_id.clone(),
        payload_json: serde_json::to_vec(&event.payload).unwrap_or_default(),
    }
}

fn game_result_to_proto(gr: &models::GameResult) -> GameResult {
    GameResult {
        winners: gr.winners.clone(),
        final_scores: gr.final_scores.clone(),
        reason: gr.reason.clone(),
    }
}

fn transition_to_proto(tr: &models::TransitionResult) -> TransitionResult {
    TransitionResult {
        game_data_json: game_data_to_bytes(&tr.game_data),
        events: tr.events.iter().map(event_to_proto).collect(),
        next_phase: Some(phase_to_proto(&tr.next_phase)),
        scores: tr.scores.clone(),
        game_over: tr.game_over.as_ref().map(game_result_to_proto),
    }
}

fn build_mcts_params(
    num_simulations: i32,
    time_limit_ms: f64,
    exploration_constant: f64,
    num_determinizations: i32,
    pw_c: f64,
    pw_alpha: f64,
    use_rave: bool,
    rave_k: f64,
    max_amaf_depth: i32,
    rave_fpu: bool,
    tile_aware_amaf: bool,
) -> MctsParams {
    let defaults = MctsParams::default();
    MctsParams {
        num_simulations: if num_simulations > 0 {
            num_simulations as usize
        } else {
            defaults.num_simulations
        },
        time_limit_ms: if time_limit_ms > 0.0 {
            time_limit_ms
        } else {
            defaults.time_limit_ms
        },
        exploration_constant: if exploration_constant > 0.0 {
            exploration_constant
        } else {
            defaults.exploration_constant
        },
        num_determinizations: if num_determinizations > 0 {
            num_determinizations as usize
        } else {
            defaults.num_determinizations
        },
        pw_c: if pw_c > 0.0 { pw_c } else { defaults.pw_c },
        pw_alpha: if pw_alpha > 0.0 {
            pw_alpha
        } else {
            defaults.pw_alpha
        },
        use_rave,
        rave_k: if rave_k > 0.0 {
            rave_k
        } else {
            defaults.rave_k
        },
        max_amaf_depth: if max_amaf_depth > 0 {
            max_amaf_depth as usize
        } else {
            defaults.max_amaf_depth
        },
        rave_fpu,
        tile_aware_amaf,
    }
}

fn resolve_eval_fn(
    eval_profile: &str,
) -> Option<
    Box<dyn Fn(&CarcassonneState, &models::Phase, &str, &[models::Player]) -> f64 + Send + Sync>,
> {
    match eval_profile {
        "aggressive" => Some(make_carcassonne_eval(&AGGRESSIVE_WEIGHTS)),
        "field_heavy" => Some(make_carcassonne_eval(&FIELD_HEAVY_WEIGHTS)),
        "conservative" => Some(make_carcassonne_eval(&CONSERVATIVE_WEIGHTS)),
        "default" => Some(make_carcassonne_eval(&DEFAULT_WEIGHTS)),
        "" => None,
        _ => None,
    }
}

#[tonic::async_trait]
impl GameEngineService for GameEngineServer {
    // --- GetGameInfo ---
    async fn get_game_info(
        &self,
        request: Request<GetGameInfoRequest>,
    ) -> Result<Response<GetGameInfoResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;

        Ok(Response::new(GetGameInfoResponse {
            game_id: plugin.game_id().to_string(),
            display_name: plugin.display_name().to_string(),
            min_players: plugin.min_players() as i32,
            max_players: plugin.max_players() as i32,
            description: plugin.description().to_string(),
            disconnect_policy: plugin.disconnect_policy().to_string(),
        }))
    }

    // --- ListGames ---
    async fn list_games(
        &self,
        _request: Request<ListGamesRequest>,
    ) -> Result<Response<ListGamesResponse>, Status> {
        let mut games = Vec::new();
        for game_id in self.registry.list_game_ids() {
            if let Some(plugin) = self.registry.get(&game_id) {
                games.push(GetGameInfoResponse {
                    game_id: plugin.game_id().to_string(),
                    display_name: plugin.display_name().to_string(),
                    min_players: plugin.min_players() as i32,
                    max_players: plugin.max_players() as i32,
                    description: plugin.description().to_string(),
                    disconnect_policy: plugin.disconnect_policy().to_string(),
                });
            }
        }
        Ok(Response::new(ListGamesResponse { games }))
    }

    // --- CreateInitialState ---
    async fn create_initial_state(
        &self,
        request: Request<CreateInitialStateRequest>,
    ) -> Result<Response<CreateInitialStateResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;
        let players = proto_to_players(&req.players);
        let config = req
            .config
            .as_ref()
            .map(proto_to_config)
            .unwrap_or(models::GameConfig {
                options: serde_json::json!({}),
                random_seed: None,
            });

        let (game_data, phase, events) = plugin.create_initial_state(&players, &config);

        Ok(Response::new(CreateInitialStateResponse {
            game_data_json: game_data_to_bytes(&game_data),
            phase: Some(phase_to_proto(&phase)),
            events: events.iter().map(event_to_proto).collect(),
        }))
    }

    // --- GetValidActions ---
    async fn get_valid_actions(
        &self,
        request: Request<GetValidActionsRequest>,
    ) -> Result<Response<GetValidActionsResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;
        let game_data = game_data_from_bytes(&req.game_data_json)?;
        let phase = req
            .phase
            .as_ref()
            .map(proto_to_phase)
            .ok_or_else(|| Status::invalid_argument("phase is required"))?;

        let valid = plugin.get_valid_actions(&game_data, &phase, &req.player_id);
        let actions_json = valid
            .iter()
            .map(|a| serde_json::to_vec(a).unwrap_or_default())
            .collect();

        Ok(Response::new(GetValidActionsResponse { actions_json }))
    }

    // --- ValidateAction ---
    async fn validate_action(
        &self,
        request: Request<ValidateActionRequest>,
    ) -> Result<Response<ValidateActionResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;
        let game_data = game_data_from_bytes(&req.game_data_json)?;
        let phase = req
            .phase
            .as_ref()
            .map(proto_to_phase)
            .ok_or_else(|| Status::invalid_argument("phase is required"))?;
        let action = req
            .action
            .as_ref()
            .map(proto_to_action)
            .ok_or_else(|| Status::invalid_argument("action is required"))?;

        let error = plugin.validate_action(&game_data, &phase, &action);
        Ok(Response::new(ValidateActionResponse { error }))
    }

    // --- ApplyAction ---
    async fn apply_action(
        &self,
        request: Request<ApplyActionRequest>,
    ) -> Result<Response<ApplyActionResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;
        let game_data = game_data_from_bytes(&req.game_data_json)?;
        let phase = req
            .phase
            .as_ref()
            .map(proto_to_phase)
            .ok_or_else(|| Status::invalid_argument("phase is required"))?;
        let action = req
            .action
            .as_ref()
            .map(proto_to_action)
            .ok_or_else(|| Status::invalid_argument("action is required"))?;
        let players = proto_to_players(&req.players);

        let result = plugin.apply_action(&game_data, &phase, &action, &players);

        Ok(Response::new(ApplyActionResponse {
            result: Some(transition_to_proto(&result)),
        }))
    }

    // --- GetPlayerView ---
    async fn get_player_view(
        &self,
        request: Request<GetPlayerViewRequest>,
    ) -> Result<Response<GetPlayerViewResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;
        let game_data = game_data_from_bytes(&req.game_data_json)?;
        let phase = req
            .phase
            .as_ref()
            .map(proto_to_phase)
            .ok_or_else(|| Status::invalid_argument("phase is required"))?;
        let players = proto_to_players(&req.players);

        let view = plugin.get_player_view(
            &game_data,
            &phase,
            req.player_id.as_deref(),
            &players,
        );
        let view_json = serde_json::to_vec(&view).unwrap_or_default();

        Ok(Response::new(GetPlayerViewResponse { view_json }))
    }

    // --- GetSpectatorSummary ---
    async fn get_spectator_summary(
        &self,
        request: Request<GetSpectatorSummaryRequest>,
    ) -> Result<Response<GetSpectatorSummaryResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;
        let game_data = game_data_from_bytes(&req.game_data_json)?;
        let phase = req
            .phase
            .as_ref()
            .map(proto_to_phase)
            .ok_or_else(|| Status::invalid_argument("phase is required"))?;
        let players = proto_to_players(&req.players);

        let summary = plugin.get_spectator_summary(&game_data, &phase, &players);
        let summary_json = serde_json::to_vec(&summary).unwrap_or_default();

        Ok(Response::new(GetSpectatorSummaryResponse { summary_json }))
    }

    // --- StateToAiView ---
    async fn state_to_ai_view(
        &self,
        request: Request<StateToAiViewRequest>,
    ) -> Result<Response<StateToAiViewResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;
        let game_data = game_data_from_bytes(&req.game_data_json)?;
        let phase = req
            .phase
            .as_ref()
            .map(proto_to_phase)
            .ok_or_else(|| Status::invalid_argument("phase is required"))?;
        let players = proto_to_players(&req.players);

        let ai_view = plugin.state_to_ai_view(&game_data, &phase, &req.player_id, &players);
        let ai_view_json = serde_json::to_vec(&ai_view).unwrap_or_default();

        Ok(Response::new(StateToAiViewResponse { ai_view_json }))
    }

    // --- ParseAiAction ---
    async fn parse_ai_action(
        &self,
        request: Request<ParseAiActionRequest>,
    ) -> Result<Response<ParseAiActionResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;
        let response_data: serde_json::Value = serde_json::from_slice(&req.response_json)
            .map_err(|e| Status::invalid_argument(format!("invalid response JSON: {}", e)))?;
        let phase = req
            .phase
            .as_ref()
            .map(proto_to_phase)
            .ok_or_else(|| Status::invalid_argument("phase is required"))?;

        let action = plugin.parse_ai_action(&response_data, &phase, &req.player_id);

        Ok(Response::new(ParseAiActionResponse {
            action: Some(Action {
                action_type: action.action_type,
                player_id: action.player_id,
                payload_json: serde_json::to_vec(&action.payload).unwrap_or_default(),
            }),
        }))
    }

    // --- OnPlayerForfeit ---
    async fn on_player_forfeit(
        &self,
        request: Request<OnPlayerForfeitRequest>,
    ) -> Result<Response<OnPlayerForfeitResponse>, Status> {
        let req = request.into_inner();
        let plugin = self.get_plugin(&req.game_id)?;
        let game_data = game_data_from_bytes(&req.game_data_json)?;
        let phase = req
            .phase
            .as_ref()
            .map(proto_to_phase)
            .ok_or_else(|| Status::invalid_argument("phase is required"))?;
        let players = proto_to_players(&req.players);

        let result = plugin.on_player_forfeit(&game_data, &phase, &req.player_id, &players);

        Ok(Response::new(OnPlayerForfeitResponse {
            result: result.map(|tr| transition_to_proto(&tr)),
        }))
    }

    // --- MctsSearch ---
    async fn mcts_search(
        &self,
        request: Request<MctsSearchRequest>,
    ) -> Result<Response<MctsSearchResponse>, Status> {
        let req = request.into_inner();
        let game_data = game_data_from_bytes(&req.game_data_json)?;
        let phase = req
            .phase
            .as_ref()
            .map(proto_to_phase)
            .ok_or_else(|| Status::invalid_argument("phase is required"))?;
        let mut players = proto_to_players(&req.players);

        // Reconstruct players from game_data scores if not provided
        if players.is_empty() {
            if let Some(scores) = game_data.get("scores").and_then(|s| s.as_object()) {
                let mut pids: Vec<&String> = scores.keys().collect();
                pids.sort();
                for (i, pid) in pids.iter().enumerate() {
                    players.push(models::Player {
                        player_id: pid.to_string(),
                        display_name: pid.to_string(),
                        seat_index: i as i32,
                        is_bot: true,
                        bot_id: None,
                    });
                }
            }
        }

        let params = build_mcts_params(
            req.num_simulations,
            req.time_limit_ms,
            req.exploration_constant,
            req.num_determinizations,
            req.pw_c,
            req.pw_alpha,
            req.use_rave,
            req.rave_k,
            req.max_amaf_depth,
            req.rave_fpu,
            req.tile_aware_amaf,
        );

        let t0 = Instant::now();

        let (action, iterations_run) = match req.game_id.as_str() {
            "carcassonne" => {
                let plugin = CarcassonnePlugin;
                let eval_fn = resolve_eval_fn(&req.eval_profile);
                let state = plugin.decode_state(&game_data);
                let eval_ref = eval_fn.as_ref().map(|f| {
                    f.as_ref()
                        as &(dyn Fn(
                            &CarcassonneState,
                            &models::Phase,
                            &str,
                            &[models::Player],
                        ) -> f64
                            + Sync)
                });
                mcts_search(
                    &state,
                    &phase,
                    &req.player_id,
                    &plugin,
                    &players,
                    &params,
                    eval_ref,
                )
            }
            "tictactoe" => {
                let plugin = TicTacToePlugin;
                let state = plugin.decode_state(&game_data);
                mcts_search(
                    &state,
                    &phase,
                    &req.player_id,
                    &plugin,
                    &players,
                    &params,
                    None::<&(dyn Fn(&crate::games::tictactoe::TicTacToeState, &models::Phase, &str, &[models::Player]) -> f64 + Sync)>,
                )
            }
            _ => {
                return Err(Status::unimplemented(format!(
                    "MCTS not available for game: {}",
                    req.game_id
                )))
            }
        };

        let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;

        Ok(Response::new(MctsSearchResponse {
            action_json: serde_json::to_vec(&action).unwrap_or_default(),
            iterations_run: iterations_run as i32,
            elapsed_ms,
        }))
    }

    // --- RunArena (server streaming) ---
    type RunArenaStream = ReceiverStream<Result<ArenaProgressUpdate, Status>>;

    async fn run_arena(
        &self,
        request: Request<RunArenaRequest>,
    ) -> Result<Response<Self::RunArenaStream>, Status> {
        let req = request.into_inner();

        let (tx, rx) = mpsc::channel(32);

        tokio::task::spawn_blocking(move || {
            let game_options = if req.game_options.is_empty() {
                None
            } else {
                let map: serde_json::Map<String, serde_json::Value> = req
                    .game_options
                    .iter()
                    .map(|(k, v)| {
                        let val = serde_json::from_str(v)
                            .unwrap_or(serde_json::Value::String(v.clone()));
                        (k.clone(), val)
                    })
                    .collect();
                Some(serde_json::Value::Object(map))
            };

            let tx_progress = tx.clone();
            let num_games = req.num_games as usize;

            let result = match req.game_id.as_str() {
                "carcassonne" => {
                    let plugin = CarcassonnePlugin;
                    let mut strategies: HashMap<
                        String,
                        Box<dyn BotStrategy<CarcassonnePlugin>>,
                    > = HashMap::new();
                    for strat_config in &req.strategies {
                        let strategy: Box<dyn BotStrategy<CarcassonnePlugin>> =
                            match strat_config.strategy_type.as_str() {
                                "random" => Box::new(RandomStrategy),
                                "mcts" => {
                                    let params = build_mcts_params(
                                        strat_config.num_simulations,
                                        strat_config.time_limit_ms,
                                        0.0,
                                        strat_config.num_determinizations,
                                        strat_config.pw_c,
                                        strat_config.pw_alpha,
                                        strat_config.use_rave,
                                        strat_config.rave_k,
                                        strat_config.max_amaf_depth,
                                        strat_config.rave_fpu,
                                        strat_config.tile_aware_amaf,
                                    );
                                    let eval_fn =
                                        resolve_eval_fn(&strat_config.eval_profile);
                                    Box::new(MctsStrategy::<CarcassonnePlugin> {
                                        params,
                                        eval_fn,
                                    })
                                }
                                _ => Box::new(RandomStrategy),
                            };
                        strategies.insert(strat_config.name.clone(), strategy);
                    }
                    let num_players = strategies.len();
                    run_arena(
                        &plugin,
                        &strategies,
                        num_games,
                        req.base_seed as u64,
                        num_players,
                        game_options,
                        req.alternate_seats,
                        Some(&|completed, total| {
                            let _ = tx_progress.blocking_send(Ok(ArenaProgressUpdate {
                                games_completed: completed as i32,
                                total_games: total as i32,
                                final_result: None,
                            }));
                        }),
                    )
                }
                _ => {
                    let _ = tx.blocking_send(Err(Status::unimplemented(format!(
                        "Arena not available for game: {}",
                        req.game_id
                    ))));
                    return;
                }
            };

            // Build final result
            let mut score_stats = HashMap::new();
            for name in result.wins.keys() {
                let (ci_lo, ci_hi) = result.confidence_interval_95(name);
                score_stats.insert(
                    name.clone(),
                    ArenaScoreStats {
                        avg: result.avg_score(name),
                        stddev: result.score_stddev(name),
                        win_rate: result.win_rate(name),
                        ci_95_lo: ci_lo,
                        ci_95_hi: ci_hi,
                    },
                );
            }

            let total_duration_s = result.game_durations_ms.iter().sum::<f64>() / 1000.0;
            let final_result = ArenaFinalResult {
                num_games: result.num_games as i32,
                wins: result
                    .wins
                    .iter()
                    .map(|(k, v)| (k.clone(), *v as i32))
                    .collect(),
                draws: result.draws as i32,
                score_stats,
                total_duration_s,
            };

            let _ = tx.blocking_send(Ok(ArenaProgressUpdate {
                games_completed: num_games as i32,
                total_games: num_games as i32,
                final_result: Some(final_result),
            }));
        });

        Ok(Response::new(ReceiverStream::new(rx)))
    }
}
