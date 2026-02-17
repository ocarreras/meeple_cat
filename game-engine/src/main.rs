use std::net::SocketAddr;
use std::path::PathBuf;

use clap::Parser;
use tonic::transport::Server;
use tracing_subscriber::EnvFilter;

mod engine;
mod games;
mod server;

use engine::plugin::JsonAdapter;
use games::carcassonne::plugin::CarcassonnePlugin;
use games::einstein_dojo::plugin::EinsteinDojoPlugin;
use games::GameRegistry;
use server::proto::game_engine_service_server::GameEngineServiceServer;
use server::GameEngineServer;

#[derive(Parser)]
#[command(name = "meeple-game-engine", about = "Meeple game engine gRPC server")]
struct Cli {
    /// Port to listen on
    #[arg(short, long, default_value = "50051", env = "MEEPLE_ENGINE_PORT")]
    port: u16,

    /// Path to bot_profiles.toml (default: auto-discover)
    #[arg(long, env = "MEEPLE_BOT_PROFILES")]
    profiles: Option<PathBuf>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env().add_directive("info".parse()?))
        .init();

    let cli = Cli::parse();

    let mut registry = GameRegistry::new();
    registry.register(Box::new(JsonAdapter(CarcassonnePlugin)));
    registry.register(Box::new(JsonAdapter(EinsteinDojoPlugin)));
    tracing::info!(
        games = ?registry.list_game_ids(),
        "registered game plugins"
    );

    let server = if let Some(ref profiles_path) = cli.profiles {
        GameEngineServer::with_profiles(registry, profiles_path)
            .map_err(|e| format!("Failed to load profiles: {}", e))?
    } else {
        GameEngineServer::new(registry)
    };

    let addr: SocketAddr = ([0, 0, 0, 0], cli.port).into();
    tracing::info!(%addr, "starting gRPC server");

    Server::builder()
        .add_service(GameEngineServiceServer::new(server))
        .serve(addr)
        .await?;

    Ok(())
}
