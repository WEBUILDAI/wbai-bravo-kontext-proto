"""Pulumi-Einstiegspunkt für den Stack ``proto``."""

import pulumi

from bravo_infra.stack import InfraSettings, build

config = pulumi.Config()
defaults = InfraSettings(owner="unset@example.invalid")
settings = InfraSettings(
    owner=config.require("owner"),
    location=pulumi.Config("azure-native").get("location") or defaults.location,
    resource_group_name=config.get("resourceGroupName") or defaults.resource_group_name,
    image=config.get("image") or defaults.image,
    budget_amount=float(config.get("budgetAmount") or defaults.budget_amount),
    budget_start_date=config.get("budgetStartDate") or defaults.budget_start_date,
    wissen_repo=config.get("wissenRepo") or defaults.wissen_repo,
    sample_repo=config.get("sampleRepo") or defaults.sample_repo,
)

for key, value in build(settings).items():
    pulumi.export(key, value)
