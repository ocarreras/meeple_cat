pub mod carcassonne;
pub mod einstein_dojo;

use std::collections::HashMap;

use crate::engine::plugin::GamePlugin;

/// Registry of available game plugins.
pub struct GameRegistry {
    plugins: HashMap<String, Box<dyn GamePlugin>>,
}

impl GameRegistry {
    pub fn new() -> Self {
        Self {
            plugins: HashMap::new(),
        }
    }

    pub fn register(&mut self, plugin: Box<dyn GamePlugin>) {
        let id = plugin.game_id().to_string();
        self.plugins.insert(id, plugin);
    }

    pub fn get(&self, game_id: &str) -> Option<&dyn GamePlugin> {
        self.plugins.get(game_id).map(|p| p.as_ref())
    }

    pub fn list_game_ids(&self) -> Vec<String> {
        self.plugins.keys().cloned().collect()
    }
}
