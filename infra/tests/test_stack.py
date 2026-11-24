"""Unit-Tests für den Pulumi-Stack mit Mocks (kein Azure-Zugriff)."""

import pulumi
import pytest

from bravo_infra.tags import make_tags

CREATED: list[pulumi.runtime.MockResourceArgs] = []
TEST_OWNER = "owner@example.invalid"

REQUIRED_TAGS = {
    "environment": "nonprod",
    "stage": "prototype",
    "project": "bravo",
    "owner": TEST_OWNER,
    "expires": "2027-02-24",
}
# Diese Typen unterstützen in Azure keine Tags.
UNTAGGABLE = {
    "azure-native:authorization:RoleAssignment",
    "azure-native:consumption:Budget",
}


class Mocks(pulumi.runtime.Mocks):
    def new_resource(self, args: pulumi.runtime.MockResourceArgs):
        CREATED.append(args)
        outputs = dict(args.inputs)
        if args.typ == "azure-native:keyvault:Vault":
            outputs["properties"] = {
                **args.inputs.get("properties", {}),
                "vaultUri": "https://kv-wbai-bravo-proto.vault.azure.net/",
            }
        if args.typ == "azure-native:managedidentity:UserAssignedIdentity":
            outputs["principalId"] = "00000000-0000-0000-0000-00000000beef"
            outputs["clientId"] = "00000000-0000-0000-0000-00000000c1d0"
        if args.typ == "azure-native:app:ManagedEnvironment":
            outputs["defaultDomain"] = "nice-sea-123.germanywestcentral.azurecontainerapps.io"
        if args.typ == "azure-native:app:ContainerApp":
            outputs["latestRevisionFqdn"] = "ca.example.azurecontainerapps.io"
            # Input ist eine Liste von IDs, der Output eine Map ID -> Details.
            ids = args.inputs["identity"].get("userAssignedIdentities", [])
            outputs["identity"] = {
                "type": "UserAssigned",
                "userAssignedIdentities": {i: {} for i in ids},
            }
        return f"{args.name}_id", outputs

    def call(self, args: pulumi.runtime.MockCallArgs):
        if args.token == "azure-native:authorization:getClientConfig":
            return {
                "subscriptionId": "sub-123",
                "tenantId": "tenant-123",
                "objectId": "obj",
                "clientId": "cli",
            }
        if args.token == "azure-native:operationalinsights:getSharedKeys":
            return {"primarySharedKey": "mock-key", "secondarySharedKey": "mock-key-2"}
        return {}


pulumi.runtime.set_mocks(Mocks(), preview=False)

from bravo_infra.stack import InfraSettings, build  # noqa: E402

OUTPUTS = build(InfraSettings(owner=TEST_OWNER))


def _by_type(typ: str) -> list[pulumi.runtime.MockResourceArgs]:
    return [r for r in CREATED if r.typ == typ]


def test_make_tags_requires_owner():
    with pytest.raises(ValueError):
        make_tags("")
    assert make_tags(TEST_OWNER, extra="x")["extra"] == "x"
    assert make_tags(TEST_OWNER, stage="prod")["stage"] == "prototype"


@pulumi.runtime.test
def test_no_resource_group_created():
    def check(_):
        assert not _by_type("azure-native:resources:ResourceGroup")
        for r in CREATED:
            if "resourceGroupName" in r.inputs:
                assert r.inputs["resourceGroupName"] == "rg-wbai-bravo-proto"

    return OUTPUTS["kontextUrl"].apply(check)


@pulumi.runtime.test
def test_all_taggable_resources_have_required_tags():
    def check(_):
        assert CREATED
        for r in CREATED:
            if r.typ in UNTAGGABLE:
                continue
            assert r.inputs.get("tags") == REQUIRED_TAGS, r.name

    return OUTPUTS["kontextUrl"].apply(check)


@pulumi.runtime.test
def test_expected_names_and_skus():
    def check(_):
        names = {r.name for r in CREATED}
        assert {
            "log-wbai-bravo-proto",
            "cae-wbai-bravo-proto",
            "acrwbaibravoproto",
            "kv-wbai-bravo-proto",
            "id-wbai-bravo-kontext-proto",
            "ca-wbai-bravo-kontext-proto",
            "budget-wbai-bravo-proto",
        } <= names
        (ws,) = _by_type("azure-native:operationalinsights:Workspace")
        assert ws.inputs["sku"]["name"] == "PerGB2018"
        assert ws.inputs["retentionInDays"] == 30
        (acr,) = _by_type("azure-native:containerregistry:Registry")
        assert acr.inputs["sku"]["name"] == "Basic"
        assert acr.inputs["adminUserEnabled"] is False
        (kv,) = _by_type("azure-native:keyvault:Vault")
        assert kv.inputs["properties"]["enableRbacAuthorization"] is True
        assert kv.inputs["properties"]["sku"]["name"] == "standard"

    return OUTPUTS["kontextUrl"].apply(check)


@pulumi.runtime.test
def test_container_app_scale_resources_and_secret():
    def check(_):
        (ca,) = _by_type("azure-native:app:ContainerApp")
        template = ca.inputs["template"]
        assert template["scale"] == {"minReplicas": 0, "maxReplicas": 1}
        container = template["containers"][0]
        assert container["resources"] == {"cpu": 0.25, "memory": "0.5Gi"}
        assert ca.inputs["configuration"]["ingress"]["external"] is True
        secret = ca.inputs["configuration"]["secrets"][0]
        assert secret["keyVaultUrl"].endswith("/secrets/bravo-kontext-token")
        assert "value" not in secret
        env = {e["name"]: e for e in container["env"]}
        assert env["BRAVO_KONTEXT_TOKEN"]["secretRef"] == "bravo-kontext-token"
        assert env["BRAVO_ALLOWED_HOSTS"]["value"] == (
            "ca-wbai-bravo-kontext-proto.nice-sea-123.germanywestcentral.azurecontainerapps.io"
        )
        assert ca.inputs["identity"]["type"] == "UserAssigned"

    return OUTPUTS["kontextUrl"].apply(check)


@pulumi.runtime.test
def test_role_assignments_and_budget():
    def check(_):
        assignments = _by_type("azure-native:authorization:RoleAssignment")
        roles = sorted(r.inputs["roleDefinitionId"].rsplit("/", 1)[-1] for r in assignments)
        assert roles == sorted(
            ["7f951dda-4ed3-4680-a7ca-43fe172d538d", "4633458b-17de-408a-b874-0445c86b69e6"]
        )
        (budget,) = _by_type("azure-native:consumption:Budget")
        assert budget.inputs["amount"] == 50.0
        assert budget.inputs["timeGrain"] == "Monthly"
        assert budget.inputs["scope"] == "/subscriptions/sub-123/resourceGroups/rg-wbai-bravo-proto"
        assert budget.inputs["notifications"]["actual-gt-80"]["contactEmails"] == [TEST_OWNER]

    return OUTPUTS["kontextUrl"].apply(check)
