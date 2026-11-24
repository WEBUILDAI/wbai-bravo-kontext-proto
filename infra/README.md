# infra – Pulumi-Stack `proto`

> PROTOTYP, nonprod. `pulumi up` macht ausschließlich ein Mensch.

Deklariert in der bestehenden RG `rg-wbai-bravo-proto` (germanywestcentral):

| Ressource | Name | Eckdaten |
|---|---|---|
| Log Analytics | `log-wbai-bravo-proto` | PerGB2018, 30 Tage |
| Container Apps Env | `cae-wbai-bravo-proto` | Consumption, Logs → Log Analytics |
| Container Registry | `acrwbaibravoproto` | Basic, Admin-User aus |
| Key Vault | `kv-wbai-bravo-proto` | Standard, RBAC, Soft Delete 7 Tage |
| Managed Identity | `id-wbai-bravo-kontext-proto` | AcrPull (ACR), Key Vault Secrets User (KV) |
| Container App | `ca-wbai-bravo-kontext-proto` | 0–1 Replica, 0.25 vCPU / 0.5 Gi, Ingress extern, Port 8000 |
| Budget | `budget-wbai-bravo-proto` | 50 €/Monat auf der RG, Alerts 80 % Ist / 100 % Prognose |

Die Container App liest `BRAVO_KONTEXT_TOKEN` aus dem KV-Secret `bravo-kontext-token` per Managed Identity.

## Lokal (Mensch, mit Azure-Rechten)
```bash
make install
az login
export AZURE_STORAGE_ACCOUNT=stwbaibravostateproto
cd infra
pulumi login 'azblob://pulumi-state?storage_account=stwbaibravostateproto'
pulumi stack select proto || pulumi stack init proto --secrets-provider passphrase
pulumi config set owner <owner-adresse-aus-README> --stack proto
pulumi preview --stack proto
```

Tests laufen ohne Azure über Pulumi-Mocks: `make test`.
