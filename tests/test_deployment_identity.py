from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "write_deployment_identity.py"
SPEC = importlib.util.spec_from_file_location("write_deployment_identity", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
HUGO_SCRIPT = ROOT / ".github" / "scripts" / "resolve_manifest_hugo.py"
HUGO_SPEC = importlib.util.spec_from_file_location("resolve_manifest_hugo", HUGO_SCRIPT)
assert HUGO_SPEC and HUGO_SPEC.loader
HUGO_MODULE = importlib.util.module_from_spec(HUGO_SPEC)
HUGO_SPEC.loader.exec_module(HUGO_MODULE)

PUBLISH_SCRIPT = ROOT / ".github" / "scripts" / "publish_deployment_identity.py"
PUBLISH_SPEC = importlib.util.spec_from_file_location("publish_deployment_identity", PUBLISH_SCRIPT)
assert PUBLISH_SPEC and PUBLISH_SPEC.loader
PUBLISH_MODULE = importlib.util.module_from_spec(PUBLISH_SPEC)
PUBLISH_SPEC.loader.exec_module(PUBLISH_MODULE)
VERIFY_SCRIPT = ROOT / ".github" / "scripts" / "verify_deployment_identity.py"
VERIFY_SPEC = importlib.util.spec_from_file_location("verify_deployment_identity", VERIFY_SCRIPT)
assert VERIFY_SPEC and VERIFY_SPEC.loader
VERIFY_MODULE = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(VERIFY_MODULE)


class DeploymentIdentityTests(unittest.TestCase):
    def test_public_identity_is_minimal_versioned_and_non_secret(self) -> None:
        payload = MODULE.deployment_identity(
            source_sha="a" * 40,
            site="aspose.com",
            environment="production",
            run_id=12345,
            run_attempt=2,
            generated_at_utc="2026-07-17T12:00:00+00:00",
        )
        self.assertEqual(
            set(payload),
            {
                "schema_version",
                "kind",
                "repository",
                "source_sha",
                "site",
                "environment",
                "workflow",
                "generated_at_utc",
            },
        )
        rendered = json.dumps(payload).casefold()
        for forbidden in ("secret", "token", "password", "approval", "nonce", "transaction"):
            self.assertNotIn(forbidden, rendered)

    def test_endpoint_and_run_evidence_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = MODULE.deployment_identity(
                source_sha="b" * 40,
                site="aspose.net",
                environment="qa",
                run_id=99,
                run_attempt=1,
                generated_at_utc="2026-07-17T12:00:00+00:00",
            )
            endpoint, evidence = MODULE.write_identity(
                output_root=root / "public",
                evidence_dir=root / "evidence",
                payload=payload,
            )
            self.assertEqual(endpoint.read_bytes(), evidence.read_bytes())
            self.assertEqual(endpoint.relative_to(root / "public").as_posix(), ".well-known/homepages-deployment.json")

    def test_invalid_source_sha_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_sha"):
            MODULE.deployment_identity(
                source_sha="main",
                site="aspose.com",
                environment="production",
                run_id=1,
                run_attempt=1,
            )

    def test_workflow_resolves_homepages_checkout_and_uploads_identity(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(encoding="utf-8")
        self.assertIn("path: homepages-source", workflow)
        self.assertIn('source_sha="$(git rev-parse HEAD)"', workflow)
        self.assertIn("steps.source.outputs.source_sha", workflow)
        self.assertIn("write_deployment_identity.py", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("homepages-source/deployment-evidence/homepages-deployment.json", workflow)
        self.assertLess(workflow.index("Write deployment identity"), workflow.index("- name: Deploy\n"))
        deploy = workflow.split('- name: Deploy\n', 1)[1]
        self.assertIn("publish_deployment_identity.py", deploy)
        self.assertLess(deploy.index("hugo --config"), deploy.index("publish_deployment_identity.py"))
        self.assertLess(deploy.index("publish_deployment_identity.py"), deploy.index("create-invalidation"))

    def test_hidden_identity_upload_uses_exact_s3_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text(
                '[[deployment.targets]]\nname = "Production"\n'
                'URL = "s3://www.groupdocs.com/site/?region=us-west-2"\n',
                encoding="utf-8",
            )
            command = PUBLISH_MODULE.upload_command(
                config=config,
                target_name="Production",
                identity=Path("public/.well-known/homepages-deployment.json"),
            )
        self.assertEqual(command[:3], ["aws", "s3", "cp"])
        self.assertEqual(Path(command[3]).as_posix(), "public/.well-known/homepages-deployment.json")
        self.assertIn("s3://www.groupdocs.com/site/.well-known/homepages-deployment.json", command)
        self.assertEqual(command[-2:], ["--region", "us-west-2"])

    def test_hidden_identity_upload_preserves_registered_ceph_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text(
                '[[deployment.targets]]\nname = "production_ceph"\n'
                'URL = "s3://www-aspose-org/?endpoint=https://s3.dynabic.com&region=us-east-1"\n',
                encoding="utf-8",
            )
            command = PUBLISH_MODULE.upload_command(
                config=config,
                target_name="production_ceph",
                identity=Path("identity.json"),
            )
        self.assertIn("s3://www-aspose-org/.well-known/homepages-deployment.json", command)
        self.assertIn("--endpoint-url", command)
        self.assertIn("https://s3.dynabic.com", command)

    def test_hidden_identity_upload_rejects_ambiguous_or_non_s3_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text(
                '[[deployment.targets]]\nname = "Production"\nURL = "gs://example/"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "s3 target"):
                PUBLISH_MODULE.upload_command(
                    config=config,
                    target_name="Production",
                    identity=Path("identity.json"),
                )

    def test_identity_reconciliation_verifies_exact_original_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            identity = Path(tmp) / "homepages-deployment.json"
            payload = MODULE.deployment_identity(
                source_sha="c" * 40,
                site="groupdocs.com",
                environment="production",
                run_id=31256841587,
                run_attempt=1,
                generated_at_utc="2026-08-08T12:34:56+00:00",
            )
            identity.write_text(json.dumps(payload), encoding="utf-8")
            VERIFY_MODULE.verify_identity(
                identity=identity,
                source_sha="c" * 40,
                site="groupdocs.com",
                environment="production",
                run_id=31256841587,
                run_attempt=1,
            )

            with self.assertRaisesRegex(ValueError, "does not match"):
                VERIFY_MODULE.verify_identity(
                    identity=identity,
                    source_sha="d" * 40,
                    site="groupdocs.com",
                    environment="production",
                    run_id=31256841587,
                    run_attempt=1,
                )

    def test_identity_reconciliation_skips_build_and_content_deploy(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("reconcile_identity:", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn("Download original deployment identity evidence", workflow)
        self.assertIn("verify_deployment_identity.py", workflow)
        self.assertIn("if: ${{ !inputs.reconcile_identity }}", workflow)
        self.assertIn('if [ "${{ inputs.reconcile_identity }}" = "true" ]; then', workflow)
        self.assertIn('identity_path="deployment-evidence/reconcile/homepages-deployment.json"', workflow)
        reconciliation_branch = workflow.split(
            'if [ "${{ inputs.reconcile_identity }}" = "true" ]; then', 1
        )[1].split("fi", 1)[0]
        self.assertNotIn("hugo --config", reconciliation_branch)

    def test_conholdate_cloud_qa_uses_its_own_cloudfront_distribution(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(
            encoding="utf-8"
        )
        qa = workflow.split("conholdate.cloud:qa)", 1)[1].split(";;", 1)[0]
        production = workflow.split("conholdate.cloud:production)", 1)[1].split(";;", 1)[0]

        self.assertIn('cache_kind="cloudfront"', qa)
        self.assertIn(
            'cache_variable="CONHOLDATE_CLOUD_QA_CLOUDFRONT_DISTRIBUTION_ID"',
            qa,
        )
        self.assertIn(
            "CONHOLDATE_CLOUD_QA_CLOUDFRONT_DISTRIBUTION_ID: "
            "${{ vars.CONHOLDATE_CLOUD_QA_CLOUDFRONT_DISTRIBUTION_ID }}",
            workflow,
        )
        self.assertIn('cache_kind="none"', production)

    def test_conholdate_com_qa_resolves_cloudfront_by_exact_alias(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(
            encoding="utf-8"
        )
        qa = workflow.split("conholdate.com:qa)", 1)[1].split(";;", 1)[0]
        production = workflow.split("conholdate.com:production)", 1)[1].split(";;", 1)[0]

        self.assertIn('cache_kind="cloudfront"', qa)
        self.assertIn('cache_alias="qa.conholdate.com"', qa)
        self.assertIn("steps.map.outputs.cache_alias", workflow)
        self.assertIn("aws cloudfront list-distributions", workflow)
        self.assertIn('alias in item.get("Aliases", {}).get("Items", [])', workflow)
        self.assertIn('cache_kind="none"', production)

    def test_groupdocs_com_qa_and_production_invalidate_cloudfront_with_deploy_credentials(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(
            encoding="utf-8"
        )
        qa = workflow.split("groupdocs.com:qa)", 1)[1].split(";;", 1)[0]
        production = workflow.split("groupdocs.com:production)", 1)[1].split(";;", 1)[0]

        self.assertIn('cache_kind="cloudfront-deploy-account"', qa)
        self.assertIn('cache_alias="qa.groupdocs.com"', qa)
        self.assertIn('CACHE_KIND: ${{ steps.map.outputs.cache_kind }}', workflow)
        self.assertIn('[ "$CACHE_KIND" = "cloudfront-deploy-account" ]', workflow)
        self.assertIn('cache_kind="cloudfront-deploy-account"', production)
        self.assertIn('cache_alias="www.groupdocs.com"', production)

    def test_groupdocs_cloud_preserves_production_mapping_and_invalidates_cloudfront(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(
            encoding="utf-8"
        )
        qa = workflow.split("groupdocs.cloud:qa)", 1)[1].split(";;", 1)[0]
        production = workflow.split("groupdocs.cloud:production)", 1)[1].split(";;", 1)[0]

        self.assertIn('credential_set="sl"', qa)
        self.assertIn('cache_kind="cloudfront-deploy-account"', qa)
        self.assertIn('cache_alias="qa.groupdocs.cloud"', qa)
        self.assertIn('cache_kind="cloudfront-deploy-account"', production)
        self.assertIn('cache_alias="www.groupdocs.cloud"', production)

    def test_groupdocs_app_preserves_production_mapping_and_invalidates_cloudfront(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(
            encoding="utf-8"
        )
        qa = workflow.split("groupdocs.app:qa)", 1)[1].split(";;", 1)[0]
        production = workflow.split("groupdocs.app:production)", 1)[1].split(";;", 1)[0]

        self.assertIn('credential_set="sl"', qa)
        self.assertIn('cache_kind="cloudfront-deploy-account"', qa)
        self.assertIn('cache_alias="qa.groupdocs.app"', qa)
        self.assertIn('cache_kind="cloudfront-deploy-account"', production)
        self.assertIn('cache_alias="www.groupdocs.app"', production)

    def test_deploy_workflow_uses_resolved_site_hugo_version(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "deploy-homepage.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("resolve_manifest_hugo.py", workflow)
        self.assertIn("--manifest docs/homepage-sites-manifest.yaml", workflow)
        self.assertNotIn('hugo_version="0.162.0"', workflow)
        self.assertIn('echo "hugo_version=$hugo_version"', workflow)
        self.assertIn('HUGO_VERSION: ${{ steps.map.outputs.hugo_version }}', workflow)
        self.assertIn('hugo_extended_withdeploy_${HUGO_VERSION}_linux-amd64.tar.gz', workflow)
        self.assertIn('hugo_extended_${HUGO_VERSION}_Linux-64bit.tar.gz', workflow)

    def test_manifest_hugo_resolver_uses_exact_site_environment_contract(self) -> None:
        manifest = """sites:
  groupdocs.com:
    production_hugo: 0.161.1
    stage_hugo: '0.101.0'
  groupdocs.cloud:
    production_hugo: 0.162.0
    stage_hugo: 0.162.0
"""
        self.assertEqual(
            "0.101.0",
            HUGO_MODULE.resolve_manifest_hugo(
                manifest,
                site="groupdocs.com",
                environment="qa",
            ),
        )
        self.assertEqual(
            "0.161.1",
            HUGO_MODULE.resolve_manifest_hugo(
                manifest,
                site="groupdocs.com",
                environment="production",
            ),
        )

    def test_manifest_hugo_resolver_rejects_missing_or_invalid_contracts(self) -> None:
        with self.assertRaisesRegex(ValueError, "not registered"):
            HUGO_MODULE.resolve_manifest_hugo(
                "sites:\n",
                site="groupdocs.com",
                environment="qa",
            )
        with self.assertRaisesRegex(ValueError, "no unique valid stage_hugo"):
            HUGO_MODULE.resolve_manifest_hugo(
                "sites:\n  groupdocs.com:\n    stage_hugo: latest\n",
                site="groupdocs.com",
                environment="qa",
            )


if __name__ == "__main__":
    unittest.main()
