"""Ressourcen des Stacks ``proto``.

Die Resource Group ``rg-wbai-bravo-proto`` existiert bereits und wird nur per Name
referenziert. Dieses Modul legt sie nie an und löscht sie nie.
"""

from dataclasses import dataclass

import pulumi
from pulumi_azure_native import (
    app,
    authorization,
    consumption,
    containerregistry,
    keyvault,
    managedidentity,
    operationalinsights,
)

from bravo_infra.tags import make_tags

# Eingebaute Azure-Rollen (Definition-IDs sind tenantübergreifend gleich).
ROLE_ACR_PULL = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
ROLE_KV_SECRETS_USER = "4633458b-17de-408a-b874-0445c86b69e6"

TOKEN_SECRET_NAME = "bravo-kontext-token"  # noqa: S105 - Name, kein Wert
APP_PORT = 8000


@dataclass(frozen=True)
class InfraSettings:
    """Konfiguration des Stacks.

    Attributes:
        owner: Verantwortliche Person (E-Mail), Pflicht-Tag und Budget-Empfänger.
        location: Azure-Region.
        resource_group_name: Bestehende Resource Group (wird nur referenziert).
        image: Container-Image für die Container App.
        budget_amount: Monatsbudget in Abrechnungswährung (EUR).
        budget_start_date: Startdatum des Budgets, erster Tag eines Monats (ISO 8601).
        wissen_repo: ``owner/repo`` des Wissens-Repos.
        sample_repo: ``owner/repo`` des Sample-Repos (Ziel für Vorschläge).
    """

    owner: str
    location: str = "germanywestcentral"
    resource_group_name: str = "rg-wbai-bravo-proto"
    image: str = "mcr.microsoft.com/k8se/quickstart:latest"
    budget_amount: float = 50.0
    budget_start_date: str = "2026-12-01T00:00:00Z"
    wissen_repo: str = "WEBUILDAI/wbai-bravo-wissen-proto"
    sample_repo: str = "WEBUILDAI/wbai-bravo-sample-proto"


def _role_definition_id(subscription_id: pulumi.Input[str], role_guid: str) -> pulumi.Output[str]:
    return pulumi.Output.concat(
        "/subscriptions/",
        subscription_id,
        "/providers/Microsoft.Authorization/roleDefinitions/",
        role_guid,
    )


def build(settings: InfraSettings) -> dict[str, pulumi.Output]:
    """Deklariert alle Ressourcen des Stacks.

    Args:
        settings: Stack-Konfiguration.

    Returns:
        Stack-Outputs (Name auf Output).
    """
    tags = make_tags(settings.owner)
    rg = settings.resource_group_name
    loc = settings.location
    client = authorization.get_client_config_output()
    rg_id = pulumi.Output.concat("/subscriptions/", client.subscription_id, "/resourceGroups/", rg)

    workspace = operationalinsights.Workspace(
        "log-wbai-bravo-proto",
        workspace_name="log-wbai-bravo-proto",
        resource_group_name=rg,
        location=loc,
        sku=operationalinsights.WorkspaceSkuArgs(name="PerGB2018"),
        retention_in_days=30,
        tags=tags,
    )
    shared_keys = operationalinsights.get_shared_keys_output(
        resource_group_name=rg, workspace_name=workspace.name
    )

    environment = app.ManagedEnvironment(
        "cae-wbai-bravo-proto",
        environment_name="cae-wbai-bravo-proto",
        resource_group_name=rg,
        location=loc,
        app_logs_configuration=app.AppLogsConfigurationArgs(
            destination="log-analytics",
            log_analytics_configuration=app.LogAnalyticsConfigurationArgs(
                customer_id=workspace.customer_id,
                shared_key=pulumi.Output.secret(shared_keys.primary_shared_key),
            ),
        ),
        tags=tags,
    )

    registry = containerregistry.Registry(
        "acrwbaibravoproto",
        registry_name="acrwbaibravoproto",
        resource_group_name=rg,
        location=loc,
        sku=containerregistry.SkuArgs(name="Basic"),
        admin_user_enabled=False,
        tags=tags,
    )

    vault = keyvault.Vault(
        "kv-wbai-bravo-proto",
        vault_name="kv-wbai-bravo-proto",
        resource_group_name=rg,
        location=loc,
        properties=keyvault.VaultPropertiesArgs(
            tenant_id=client.tenant_id,
            sku=keyvault.SkuArgs(family="A", name="standard"),
            enable_rbac_authorization=True,
            enable_soft_delete=True,
            soft_delete_retention_in_days=7,
        ),
        tags=tags,
    )

    identity = managedidentity.UserAssignedIdentity(
        "id-wbai-bravo-kontext-proto",
        resource_name_="id-wbai-bravo-kontext-proto",
        resource_group_name=rg,
        location=loc,
        tags=tags,
    )

    acr_pull = authorization.RoleAssignment(
        "ra-acrpull-kontext",
        principal_id=identity.principal_id,
        principal_type="ServicePrincipal",
        role_definition_id=_role_definition_id(client.subscription_id, ROLE_ACR_PULL),
        scope=registry.id,
    )
    kv_secrets_user = authorization.RoleAssignment(
        "ra-kvsecretsuser-kontext",
        principal_id=identity.principal_id,
        principal_type="ServicePrincipal",
        role_definition_id=_role_definition_id(client.subscription_id, ROLE_KV_SECRETS_USER),
        scope=vault.id,
    )

    secret_url = vault.properties.apply(
        lambda p: f"{p.vault_uri.rstrip('/')}/secrets/{TOKEN_SECRET_NAME}"
    )
    uses_acr = settings.image.startswith("acrwbaibravoproto.")

    container_app = app.ContainerApp(
        "ca-wbai-bravo-kontext-proto",
        container_app_name="ca-wbai-bravo-kontext-proto",
        resource_group_name=rg,
        location=loc,
        managed_environment_id=environment.id,
        identity=app.ManagedServiceIdentityArgs(
            type="UserAssigned", user_assigned_identities=[identity.id]
        ),
        configuration=app.ConfigurationArgs(
            active_revisions_mode="Single",
            ingress=app.IngressArgs(external=True, target_port=APP_PORT, transport="auto"),
            registries=(
                [app.RegistryCredentialsArgs(server=registry.login_server, identity=identity.id)]
                if uses_acr
                else None
            ),
            secrets=[
                app.SecretArgs(
                    name=TOKEN_SECRET_NAME, key_vault_url=secret_url, identity=identity.id
                )
            ],
        ),
        template=app.TemplateArgs(
            containers=[
                app.ContainerArgs(
                    name="kontext",
                    image=settings.image,
                    resources=app.ContainerResourcesArgs(cpu=0.25, memory="0.5Gi"),
                    env=[
                        app.EnvironmentVarArgs(
                            name="BRAVO_KONTEXT_TOKEN", secret_ref=TOKEN_SECRET_NAME
                        ),
                        app.EnvironmentVarArgs(name="WISSEN_REPO", value=settings.wissen_repo),
                        app.EnvironmentVarArgs(name="SAMPLE_REPO", value=settings.sample_repo),
                        app.EnvironmentVarArgs(name="LOG_FORMAT", value="json"),
                        app.EnvironmentVarArgs(
                            name="BRAVO_ALLOWED_HOSTS",
                            value=pulumi.Output.concat(
                                "ca-wbai-bravo-kontext-proto.", environment.default_domain
                            ),
                        ),
                    ],
                )
            ],
            scale=app.ScaleArgs(min_replicas=0, max_replicas=1),
        ),
        tags=tags,
        opts=pulumi.ResourceOptions(depends_on=[acr_pull, kv_secrets_user]),
    )

    consumption.Budget(
        "budget-wbai-bravo-proto",
        budget_name="budget-wbai-bravo-proto",
        scope=rg_id,
        amount=settings.budget_amount,
        category="Cost",
        time_grain="Monthly",
        time_period=consumption.BudgetTimePeriodArgs(start_date=settings.budget_start_date),
        notifications={
            "actual-gt-80": consumption.NotificationArgs(
                enabled=True,
                operator="GreaterThan",
                threshold=80,
                threshold_type="Actual",
                contact_emails=[settings.owner],
            ),
            "forecast-gt-100": consumption.NotificationArgs(
                enabled=True,
                operator="GreaterThan",
                threshold=100,
                threshold_type="Forecasted",
                contact_emails=[settings.owner],
            ),
        },
    )

    fqdn = container_app.latest_revision_fqdn
    return {
        "resourceGroupId": rg_id,
        "acrLoginServer": registry.login_server,
        "keyVaultUri": vault.properties.apply(lambda p: p.vault_uri),
        "identityClientId": identity.client_id,
        "logAnalyticsWorkspaceId": workspace.customer_id,
        "kontextUrl": fqdn.apply(lambda f: f"https://{f}" if f else ""),
    }
