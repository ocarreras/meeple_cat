//! Arena CLI — run bot-vs-bot experiments from the command line.
//!
//! Usage:
//!   cargo run --release --bin arena -- --games 100 --p1-profile hard --p2-profile easy
//!   cargo run --release --bin arena -- --games 50 --p1-sims 500 --p1-eval default --p2-sims 1000 --p2-eval aggressive

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use clap::Parser;

use meeple_game_engine::engine::arena::run_arena;
use meeple_game_engine::engine::bot_profiles::{load_default_profiles, load_profiles, BotProfilesFile};
use meeple_game_engine::engine::bot_strategy::{BotStrategy, MctsStrategy, RandomStrategy};
use meeple_game_engine::engine::mcts::MctsParams;
use meeple_game_engine::engine::models::{Phase, Player};
use meeple_game_engine::games::carcassonne::evaluator::*;
use meeple_game_engine::games::carcassonne::plugin::CarcassonnePlugin;
use meeple_game_engine::games::carcassonne::types::CarcassonneState;

#[derive(Parser)]
#[command(name = "arena", about = "Run bot-vs-bot arena experiments for Carcassonne")]
struct Cli {
    /// Number of games to play
    #[arg(long, default_value = "100")]
    games: usize,

    /// Random seed
    #[arg(long, default_value = "42")]
    seed: u64,

    /// Alternate seat positions between games
    #[arg(long, default_value = "true")]
    alternate_seats: bool,

    /// Path to bot_profiles.toml
    #[arg(long)]
    profiles: Option<PathBuf>,

    // --- Player 1 ---
    /// P1 display name
    #[arg(long, default_value = "p1")]
    p1_name: String,

    /// P1 profile name (from bot_profiles.toml)
    #[arg(long)]
    p1_profile: Option<String>,

    /// P1 strategy type: "mcts" or "random"
    #[arg(long, default_value = "mcts")]
    p1_type: String,

    /// P1 MCTS simulations
    #[arg(long)]
    p1_sims: Option<usize>,

    /// P1 MCTS time limit (ms)
    #[arg(long)]
    p1_time: Option<f64>,

    /// P1 determinizations
    #[arg(long)]
    p1_dets: Option<usize>,

    /// P1 eval profile: "default", "aggressive", "field_heavy", "conservative"
    #[arg(long)]
    p1_eval: Option<String>,

    /// P1 exploration constant
    #[arg(long)]
    p1_exploration: Option<f64>,

    /// P1 progressive widening constant
    #[arg(long)]
    p1_pw_c: Option<f64>,

    /// P1 progressive widening exponent
    #[arg(long)]
    p1_pw_alpha: Option<f64>,

    /// P1 enable RAVE
    #[arg(long)]
    p1_rave: bool,

    /// P1 RAVE k parameter
    #[arg(long)]
    p1_rave_k: Option<f64>,

    /// P1 max AMAF depth
    #[arg(long)]
    p1_max_amaf_depth: Option<usize>,

    /// P1 enable RAVE first-play urgency
    #[arg(long)]
    p1_rave_fpu: bool,

    /// P1 enable tile-aware AMAF
    #[arg(long)]
    p1_tile_aware_amaf: bool,

    // --- Player 2 ---
    /// P2 display name
    #[arg(long, default_value = "p2")]
    p2_name: String,

    /// P2 profile name (from bot_profiles.toml)
    #[arg(long)]
    p2_profile: Option<String>,

    /// P2 strategy type: "mcts" or "random"
    #[arg(long, default_value = "mcts")]
    p2_type: String,

    /// P2 MCTS simulations
    #[arg(long)]
    p2_sims: Option<usize>,

    /// P2 MCTS time limit (ms)
    #[arg(long)]
    p2_time: Option<f64>,

    /// P2 determinizations
    #[arg(long)]
    p2_dets: Option<usize>,

    /// P2 eval profile
    #[arg(long)]
    p2_eval: Option<String>,

    /// P2 exploration constant
    #[arg(long)]
    p2_exploration: Option<f64>,

    /// P2 progressive widening constant
    #[arg(long)]
    p2_pw_c: Option<f64>,

    /// P2 progressive widening exponent
    #[arg(long)]
    p2_pw_alpha: Option<f64>,

    /// P2 enable RAVE
    #[arg(long)]
    p2_rave: bool,

    /// P2 RAVE k parameter
    #[arg(long)]
    p2_rave_k: Option<f64>,

    /// P2 max AMAF depth
    #[arg(long)]
    p2_max_amaf_depth: Option<usize>,

    /// P2 enable RAVE first-play urgency
    #[arg(long)]
    p2_rave_fpu: bool,

    /// P2 enable tile-aware AMAF
    #[arg(long)]
    p2_tile_aware_amaf: bool,
}

fn resolve_eval(
    eval_profile: &str,
    custom_weights: Option<&EvalWeights>,
) -> Option<Box<dyn Fn(&CarcassonneState, &Phase, &str, &[Player]) -> f64 + Send + Sync>> {
    if let Some(w) = custom_weights {
        return Some(make_carcassonne_eval_owned(*w));
    }
    match eval_profile {
        "aggressive" => Some(make_carcassonne_eval(&AGGRESSIVE_WEIGHTS)),
        "field_heavy" => Some(make_carcassonne_eval(&FIELD_HEAVY_WEIGHTS)),
        "conservative" => Some(make_carcassonne_eval(&CONSERVATIVE_WEIGHTS)),
        "default" => Some(make_carcassonne_eval(&DEFAULT_WEIGHTS)),
        "" => None,
        other => {
            eprintln!("Warning: unknown eval profile '{}', using default", other);
            Some(make_carcassonne_eval(&DEFAULT_WEIGHTS))
        }
    }
}

struct PlayerConfig {
    name: String,
    strategy_type: String,
    params: MctsParams,
    eval_profile: String,
    custom_weights: Option<EvalWeights>,
}

fn build_player_config(
    name: &str,
    profile_name: Option<&str>,
    strategy_type: &str,
    sims: Option<usize>,
    time: Option<f64>,
    dets: Option<usize>,
    eval: Option<&str>,
    exploration: Option<f64>,
    pw_c: Option<f64>,
    pw_alpha: Option<f64>,
    rave: bool,
    rave_k: Option<f64>,
    max_amaf_depth: Option<usize>,
    rave_fpu: bool,
    tile_aware_amaf: bool,
    profiles: &BotProfilesFile,
) -> PlayerConfig {
    // Start from profile if specified
    if let Some(prof_name) = profile_name {
        let profile = profiles.profiles.get(prof_name).unwrap_or_else(|| {
            eprintln!("Error: profile '{}' not found in bot_profiles.toml", prof_name);
            eprintln!("Available profiles: {:?}", profiles.profiles.keys().collect::<Vec<_>>());
            std::process::exit(1);
        });

        let mut params = profile.to_mcts_params();
        let mut eval_profile = profile.effective_eval_profile().to_string();
        let custom_weights = profile.eval_weights;

        // CLI overrides on top of profile
        if let Some(v) = sims { params.num_simulations = v; }
        if let Some(v) = time { params.time_limit_ms = v; }
        if let Some(v) = dets { params.num_determinizations = v; }
        if let Some(v) = eval { eval_profile = v.to_string(); }
        if let Some(v) = exploration { params.exploration_constant = v; }
        if let Some(v) = pw_c { params.pw_c = v; }
        if let Some(v) = pw_alpha { params.pw_alpha = v; }
        if rave { params.use_rave = true; }
        if let Some(v) = rave_k { params.rave_k = v; }
        if let Some(v) = max_amaf_depth { params.max_amaf_depth = v; }
        if rave_fpu { params.rave_fpu = true; }
        if tile_aware_amaf { params.tile_aware_amaf = true; }

        let display_name = if name == "p1" || name == "p2" {
            prof_name.to_string()
        } else {
            name.to_string()
        };

        return PlayerConfig {
            name: display_name,
            strategy_type: profile.strategy_type.clone(),
            params,
            eval_profile,
            custom_weights,
        };
    }

    // Build from individual CLI args
    let d = MctsParams::default();
    let params = MctsParams {
        num_simulations: sims.unwrap_or(d.num_simulations),
        time_limit_ms: time.unwrap_or(999999.0), // no time limit by default in arena
        exploration_constant: exploration.unwrap_or(d.exploration_constant),
        num_determinizations: dets.unwrap_or(d.num_determinizations),
        pw_c: pw_c.unwrap_or(d.pw_c),
        pw_alpha: pw_alpha.unwrap_or(d.pw_alpha),
        use_rave: rave,
        rave_k: rave_k.unwrap_or(d.rave_k),
        max_amaf_depth: max_amaf_depth.unwrap_or(d.max_amaf_depth),
        rave_fpu,
        tile_aware_amaf,
    };

    PlayerConfig {
        name: name.to_string(),
        strategy_type: strategy_type.to_string(),
        params,
        eval_profile: eval.unwrap_or("default").to_string(),
        custom_weights: None,
    }
}

fn build_strategy(
    config: &PlayerConfig,
) -> Box<dyn BotStrategy<CarcassonnePlugin>> {
    match config.strategy_type.as_str() {
        "random" => Box::new(RandomStrategy),
        "mcts" | _ => {
            let eval_fn = resolve_eval(&config.eval_profile, config.custom_weights.as_ref());
            match eval_fn {
                Some(f) => Box::new(MctsStrategy::<CarcassonnePlugin>::with_eval(
                    config.params.clone(),
                    f,
                )),
                None => Box::new(MctsStrategy::<CarcassonnePlugin>::new(config.params.clone())),
            }
        }
    }
}

fn print_config(label: &str, config: &PlayerConfig) {
    eprintln!("  {}: type={}, sims={}, time={:.0}ms, dets={}, eval={}, pw_c={}, pw_alpha={}, rave={}{}",
        label,
        config.strategy_type,
        config.params.num_simulations,
        config.params.time_limit_ms,
        config.params.num_determinizations,
        config.eval_profile,
        config.params.pw_c,
        config.params.pw_alpha,
        config.params.use_rave,
        if config.custom_weights.is_some() { " [custom weights]" } else { "" },
    );
    if config.params.use_rave {
        eprintln!("         rave_k={}, max_amaf_depth={}, rave_fpu={}, tile_aware_amaf={}",
            config.params.rave_k,
            config.params.max_amaf_depth,
            config.params.rave_fpu,
            config.params.tile_aware_amaf,
        );
    }
}

fn main() {
    let cli = Cli::parse();

    // Load profiles
    let profiles = match &cli.profiles {
        Some(path) => load_profiles(path).unwrap_or_else(|e| {
            eprintln!("Error loading profiles: {}", e);
            std::process::exit(1);
        }),
        None => load_default_profiles(),
    };

    // Build player configs
    let p1_config = build_player_config(
        &cli.p1_name, cli.p1_profile.as_deref(), &cli.p1_type,
        cli.p1_sims, cli.p1_time, cli.p1_dets, cli.p1_eval.as_deref(),
        cli.p1_exploration, cli.p1_pw_c, cli.p1_pw_alpha,
        cli.p1_rave, cli.p1_rave_k, cli.p1_max_amaf_depth,
        cli.p1_rave_fpu, cli.p1_tile_aware_amaf,
        &profiles,
    );

    let p2_config = build_player_config(
        &cli.p2_name, cli.p2_profile.as_deref(), &cli.p2_type,
        cli.p2_sims, cli.p2_time, cli.p2_dets, cli.p2_eval.as_deref(),
        cli.p2_exploration, cli.p2_pw_c, cli.p2_pw_alpha,
        cli.p2_rave, cli.p2_rave_k, cli.p2_max_amaf_depth,
        cli.p2_rave_fpu, cli.p2_tile_aware_amaf,
        &profiles,
    );

    // Print configuration
    eprintln!("Arena: {} games, seed={}, alternate_seats={}", cli.games, cli.seed, cli.alternate_seats);
    print_config(&p1_config.name, &p1_config);
    print_config(&p2_config.name, &p2_config);
    eprintln!();

    // Build strategies
    let mut strategies: HashMap<String, Box<dyn BotStrategy<CarcassonnePlugin>>> = HashMap::new();
    strategies.insert(p1_config.name.clone(), build_strategy(&p1_config));
    strategies.insert(p2_config.name.clone(), build_strategy(&p2_config));

    // Progress tracking
    let completed = Arc::new(AtomicUsize::new(0));
    let total = cli.games;

    let completed_ref = completed.clone();
    let progress_cb = move |done: usize, _total: usize| {
        completed_ref.store(done, Ordering::Relaxed);
        eprint!("\r  [{}/{}] games completed", done, total);
    };

    let plugin = CarcassonnePlugin;
    let result = run_arena(
        &plugin,
        &strategies,
        cli.games,
        cli.seed,
        2,
        None,
        cli.alternate_seats,
        Some(&progress_cb),
    );

    eprintln!("\r                                    "); // clear progress line
    println!("{}", result.summary());
}
