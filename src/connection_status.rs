use hbb_common::{anyhow::anyhow, tokio, ResultType};
use librustdesk::ipc::{self, Data};

async fn read_status() -> ResultType<serde_json::Value> {
    let mut connection = ipc::connect(2000, "").await?;
    connection.send(&Data::OnlineStatus(None)).await?;
    let (online, key_confirmed) = match connection.next_timeout(2000).await? {
        Some(Data::OnlineStatus(Some(status))) => status,
        _ => return Err(anyhow!("Missing OnlineStatus response")),
    };
    connection.send(&Data::Config(("id".to_owned(), None))).await?;
    let id_present = match connection.next_timeout(2000).await? {
        Some(Data::Config((name, Some(value)))) if name == "id" => !value.is_empty(),
        _ => return Err(anyhow!("Missing ID response")),
    };
    Ok(serde_json::json!({
        "ipc_connected": true,
        "online": online > 0,
        "key_confirmed": key_confirmed,
        "id_present": id_present,
        "ready": online > 0 && key_confirmed && id_present,
    }))
}

// This is a top-level CLI entry point, called before the GUI/runtime starts.
#[tokio::main(flavor = "current_thread")]
pub async fn run() {
    let result = match read_status().await {
        Ok(status) => status,
        Err(error) => serde_json::json!({"ipc_connected": false, "ready": false, "error": error.to_string()}),
    };
    println!("{}", result);
}
