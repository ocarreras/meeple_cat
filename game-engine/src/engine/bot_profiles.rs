//! Named bot profiles: bundles of MCTS params + evaluator weights.
//! Loaded from TOML at runtime for arena CLI and gRPC server.

use std::collections::HashMap;
use std::path::Path;

use serde::Deserialize;

use crate::engine::mcts::MctsParams;
use crate::games::carcassonne::evaluator::EvalWeights;

/// A named bot profile combining MCTS parameters and evaluator configuration.
#[derive(Debug, Deserialize, Clone)]
pub struct BotProfile {
    pub description: Option<String>,
    #[serde(default = "default_strategy_type")]
    pub strategy_type: String,

    // MCTS params (all optional — defaults from MctsParams::default())
    pub num_simulations: Option<usize>,
    pub time_limit_ms: Option<f64>,
    pub exploration_constant: Option<f64>,
    pub num_determinizations: Option<usize>,
    pub pw_c: Option<f64>,
    pub pw_alpha: Option<f64>,
    pub use_rave: Option<bool>,
    pub rave_k: Option<f64>,
    pub max_amaf_depth: Option<usize>,
    pub rave_fpu: Option<bool>,
    pub tile_aware_amaf: Option<bool>,

    /// Named evaluator preset: "default", "aggressive", "field_heavy", "conservative".
    pub eval_profile: Option<String>,
    /// Custom eval weights (overrides eval_profile when present).
    pub eval_weights: Option<EvalWeights>,
}

fn default_strategy_type() -> String {
    "mcts".into()
}

/// Maps difficulty tiers to profile names.
#[derive(Debug, Deserialize, Clone, Default)]
pub struct ProductionConfig {
    pub easy: Option<String>,
    pub medium: Option<String>,
    pub hard: Option<String>,
    pub default: Option<String>,
}

/// Top-level TOML file structure.
#[derive(Debug, Deserialize, Clone)]
pub struct BotProfilesFile {
    #[serde(default)]
    pub profiles: HashMap<String, BotProfile>,
    #[serde(default)]
    pub production: ProductionConfig,
}

impl BotProfile {
    /// Convert to MctsParams, using defaults for any unspecified fields.
    pub fn to_mcts_params(&self) -> MctsParams {
        let d = MctsParams::default();
        MctsParams {
            num_simulations: self.num_simulations.unwrap_or(d.num_simulations),
            time_limit_ms: self.time_limit_ms.unwrap_or(d.time_limit_ms),
            exploration_constant: self.exploration_constant.unwrap_or(d.exploration_constant),
            num_determinizations: self.num_determinizations.unwrap_or(d.num_determinizations),
            pw_c: self.pw_c.unwrap_or(d.pw_c),
            pw_alpha: self.pw_alpha.unwrap_or(d.pw_alpha),
            use_rave: self.use_rave.unwrap_or(d.use_rave),
            rave_k: self.rave_k.unwrap_or(d.rave_k),
            max_amaf_depth: self.max_amaf_depth.unwrap_or(d.max_amaf_depth),
            rave_fpu: self.rave_fpu.unwrap_or(d.rave_fpu),
            tile_aware_amaf: self.tile_aware_amaf.unwrap_or(d.tile_aware_amaf),
        }
    }

    /// Return the effective eval_profile string (from eval_profile field or empty).
    pub fn effective_eval_profile(&self) -> &str {
        self.eval_profile.as_deref().unwrap_or("default")
    }
}

/// Load profiles from a TOML file at the given path.
pub fn load_profiles(path: &Path) -> Result<BotProfilesFile, String> {
    let content = std::fs::read_to_string(path)
        .map_err(|e| format!("Failed to read {}: {}", path.display(), e))?;
    toml::from_str(&content).map_err(|e| format!("Failed to parse {}: {}", path.display(), e))
}

/// Try to load profiles from well-known paths, returning a default if none found.
pub fn load_default_profiles() -> BotProfilesFile {
    let candidates = [
        "bot_profiles.toml",
        "../bot_profiles.toml",
        "/etc/meeple/bot_profiles.toml",
    ];
    for path in &candidates {
        let p = Path::new(path);
        if p.exists() {
            match load_profiles(p) {
                Ok(profiles) => {
                    tracing::info!(path = %p.display(), count = profiles.profiles.len(), "loaded bot profiles");
                    return profiles;
                }
                Err(e) => {
                    tracing::warn!(path = %p.display(), error = %e, "failed to load bot profiles");
                }
            }
        }
    }
    tracing::info!("no bot_profiles.toml found, using built-in defaults");
    BotProfilesFile {
        profiles: HashMap::new(),
        production: ProductionConfig::default(),
    }
}

/// Resolve a production difficulty tier to a profile name.
impl ProductionConfig {
    pub fn resolve(&self, difficulty: &str) -> Option<&str> {
        match difficulty {
            "easy" => self.easy.as_deref(),
            "medium" => self.medium.as_deref(),
            "hard" => self.hard.as_deref(),
            _ => self.default.as_deref(),
        }
    }
}
