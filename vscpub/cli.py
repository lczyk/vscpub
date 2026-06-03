import json
from pathlib import Path

import click
import tabulate as tabulate_mod

from vscpub.client import VscClient
from vscpub.config import load_config
from vscpub.exceptions import VscpubError
from vscpub.workflows import (
    resolve_storage_policy,
    run_product_update,
    run_publish,
    run_storage_create,
    run_version_add,
)


def _make_client(ctx: click.Context) -> VscClient:
    try:
        return VscClient.from_env(dry_run=ctx.obj["dry_run"], verbose=ctx.obj["verbose"])
    except VscpubError as e:
        raise click.ClickException(str(e)) from e


@click.group()
@click.option("--dry-run", is_flag=True, help="Print API calls without executing mutations.")
@click.option("--verbose", is_flag=True, help="Log API calls to stderr.")
@click.pass_context
def cli(ctx: click.Context, dry_run: bool, verbose: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["dry_run"] = dry_run
    ctx.obj["verbose"] = verbose


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------


@cli.group()
def storage() -> None:
    pass


@storage.command("create")
@click.pass_context
def storage_create(ctx: click.Context) -> None:
    """Fetch a GCS pre-signed POST policy and print it as JSON."""
    client = _make_client(ctx)
    try:
        result = run_storage_create(client)
    except VscpubError as e:
        raise click.ClickException(str(e)) from e
    click.echo(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# product
# ---------------------------------------------------------------------------


@cli.group()
def product() -> None:
    pass


@product.command("list")
@click.pass_context
def product_list(ctx: click.Context) -> None:
    """List all products for the authenticated organisation."""
    client = _make_client(ctx)
    try:
        products = list(client.list_products())
    except VscpubError as e:
        raise click.ClickException(str(e)) from e

    if not products:
        click.echo("No products found.")
        return

    rows = [
        {
            "ID": p.get("productId", ""),
            "NAME": p.get("displayName", ""),
            "STATUS": p.get("status", ""),
            "LICENSE": p.get("solutionLicense", ""),
        }
        for p in products
    ]
    click.echo(tabulate_mod.tabulate(rows, headers="keys"))


@product.command("get")
@click.argument("product_id")
@click.pass_context
def product_get(ctx: click.Context, product_id: str) -> None:
    """Get full details for a product."""
    client = _make_client(ctx)
    try:
        result = client.get_product(product_id)
    except VscpubError as e:
        raise click.ClickException(str(e)) from e
    click.echo(json.dumps(result, indent=2))


@product.command("update")
@click.option("--storage", "storage_file", type=click.Path(exists=True), default=None)
@click.argument("yaml_file", type=click.Path(exists=True))
@click.pass_context
def product_update(ctx: click.Context, storage_file: str | None, yaml_file: str) -> None:
    """Update product metadata from a YAML config file."""
    client = _make_client(ctx)
    dry_run = ctx.obj["dry_run"]
    try:
        config = load_config(Path(yaml_file))
        storage_path = Path(storage_file) if storage_file else None
        policy = resolve_storage_policy(client, storage_path, dry_run)
        run_product_update(client, config, policy, dry_run)
    except VscpubError as e:
        raise click.ClickException(str(e)) from e
    if not dry_run:
        click.echo("Product updated.")


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@cli.group()
def version() -> None:
    pass


@version.command("get")
@click.argument("product_id")
@click.argument("version_number")
@click.pass_context
def version_get(ctx: click.Context, product_id: str, version_number: str) -> None:
    """Get details for a specific product version."""
    client = _make_client(ctx)
    try:
        result = client.get_product_version(product_id, version_number)
    except VscpubError as e:
        raise click.ClickException(str(e)) from e
    click.echo(json.dumps(result, indent=2))


@version.command("add")
@click.option("--storage", "storage_file", type=click.Path(exists=True), default=None)
@click.argument("yaml_file", type=click.Path(exists=True))
@click.pass_context
def version_add(ctx: click.Context, storage_file: str | None, yaml_file: str) -> None:
    """Add a new version to an existing product."""
    client = _make_client(ctx)
    dry_run = ctx.obj["dry_run"]
    try:
        config = load_config(Path(yaml_file))
        storage_path = Path(storage_file) if storage_file else None
        policy = resolve_storage_policy(client, storage_path, dry_run)
        result = run_version_add(client, config, policy, dry_run)
    except VscpubError as e:
        raise click.ClickException(str(e)) from e
    if not dry_run:
        click.echo(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


@cli.command("publish")
@click.option("--storage", "storage_file", type=click.Path(), default=None)
@click.argument("yaml_file", type=click.Path(exists=True))
@click.pass_context
def publish(ctx: click.Context, storage_file: str | None, yaml_file: str) -> None:
    """Full publish workflow: upload assets, update product, add version."""
    client = _make_client(ctx)
    dry_run = ctx.obj["dry_run"]
    try:
        config = load_config(Path(yaml_file))
        storage_path = Path(storage_file) if storage_file else None
        policy = resolve_storage_policy(client, storage_path, dry_run)
        result = run_publish(client, config, policy, dry_run)
    except VscpubError as e:
        raise click.ClickException(str(e)) from e
    if not dry_run:
        click.echo(json.dumps(result, indent=2))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
