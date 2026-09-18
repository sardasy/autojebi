"""Isolated integration harness. Never loads production .env credentials."""
import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "spec-validation" / "runtime.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["up", "test", "model"])
    args = parser.parse_args()
    if STATE.exists():
        config = json.loads(STATE.read_text(encoding="utf-8"))
    else:
        config = {"pg": secrets.token_hex(24), "neo4j": secrets.token_hex(24)}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with STATE.open("x", encoding="utf-8") as f:
            json.dump(config, f)
    env = {**os.environ, "SPEC_POSTGRES_PASSWORD": config["pg"], "SPEC_NEO4J_PASSWORD": config["neo4j"],
        "SPEC_NEO4J_URI": "bolt://127.0.0.1:17687", "SPEC_QDRANT_URL": "http://127.0.0.1:16333",
        "SPEC_SEARCH_ENABLED": "true", "SPEC_SEARCH_ENV": "validation",
        "SPEC_TEST_DATABASE_URL": f"postgresql+psycopg://spec_validation:{config['pg']}@127.0.0.1:15433/spec_validation",
        "SPEC_LIVE_TEST": "true", "HF_HUB_DISABLE_PROGRESS_BARS": "1"}
    if args.command == "up":
        result = subprocess.run(["docker", "compose", "-f", str(ROOT / "infra/docker-compose.spec-validation.yml"), "up", "-d"],
                                env=env, cwd=ROOT, check=False)
        sys.exit(result.returncode)
    if args.command == "model":
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        from huggingface_hub import HfApi, snapshot_download
        revision = HfApi().model_info("BAAI/bge-m3").sha
        snapshot = snapshot_download("BAAI/bge-m3", revision=revision,
            local_dir=str(STATE.parent / "models" / "snapshots" / revision),
            allow_patterns=["*.json", "*.safetensors", "*.model", "pytorch_model.bin", "1_Pooling/*"],
            ignore_patterns=["onnx/*"])
        if not any(Path(snapshot).glob("*.safetensors")) and not (Path(snapshot) / "pytorch_model.bin").is_file():
            raise RuntimeError("Model weights are missing; snapshot is not ready")
        config.update(revision=revision, snapshot=snapshot)
        STATE.write_text(json.dumps(config), encoding="utf-8")
        print("Local immutable BGE-M3 snapshot ready:", revision)
        return
    env["SPEC_BGE_REVISION"] = config.get("revision", "")
    env["SPEC_BGE_SNAPSHOT"] = config.get("snapshot", "")
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/test_spec_live.py", "-q", "-rA"],
                            env=env, cwd=ROOT, check=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
