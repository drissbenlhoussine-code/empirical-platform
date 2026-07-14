param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("up", "down", "config")]
    [string]$Action
)

$ComposeFile = "infra/local/compose.yaml"

if ($Action -eq "config") {
    docker compose -f $ComposeFile config
} elseif ($Action -eq "up") {
    docker compose -f $ComposeFile up -d
} elseif ($Action -eq "down") {
    docker compose -f $ComposeFile down
}

