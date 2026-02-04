#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import re

try:
    import yaml
except Exception:
    print("Missing dependency: pyyaml. Run `pip install pyyaml` and retry.")
    sys.exit(2)

CONFIG_PATH = Path(".openclaw/config.yaml")
ENV_PATH = Path(".env")

PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z0-9_]+)\}")

def load_config(path: Path):
    if not path.exists():
        print(f"Config file not found: {path}")
        return None
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_dotenv(path: Path):
    env = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        env[k] = v
    return env


def resolve_placeholders(obj, env_map):
    if isinstance(obj, str):
        def repl(m):
            name = m.group(1)
            return env_map.get(name, os.getenv(name, m.group(0)))
        return PLACEHOLDER_RE.sub(repl, obj)
    if isinstance(obj, dict):
        return {k: resolve_placeholders(v, env_map) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_placeholders(v, env_map) for v in obj]
    return obj

def main():
    # Load .env and inject into environment for this validation run (without overwriting existing vars)
    dotenv = load_dotenv(ENV_PATH)
    for k, v in dotenv.items():
        if not os.getenv(k):
            os.environ[k] = v

    cfg = load_config(CONFIG_PATH)
    if cfg is None:
        sys.exit(1)

    providers = cfg.get("providers")
    if not providers:
        print("No 'providers' section found in config.")
        sys.exit(1)

    print("Providers found:")
    for name, info in providers.items():
        print(f"- {name}")
        base = info.get("baseUrl")
        print(f"  baseUrl: {base}")
        api = info.get("api")
        print(f"  api: {api}")
        models = info.get("models") or []
        print(f"  models: {len(models)} entries")
        for m in models:
            print(f"    - id: {m.get('id')} name: {m.get('name')}")

        # Resolve placeholders using env (including values from .env)
        resolved_info = resolve_placeholders(info, dotenv)
        apiKey = resolved_info.get("apiKey")
        if apiKey and isinstance(apiKey, str) and not apiKey.startswith("${"):
            masked = apiKey[:4] + "..." + apiKey[-4:] if len(apiKey) > 8 else "****"
            print(f"  apiKey injected (masked): {masked}")
        else:
            # fallback: detect candidate env var names
            env_var_candidates = []
            orig_apiKey = info.get("apiKey")
            if isinstance(orig_apiKey, str) and orig_apiKey.startswith("${") and orig_apiKey.endswith("}"):
                env_var_candidates.append(orig_apiKey[2:-1])
            env_var_candidates.append(f"OPENCLAW_{name.upper()}_API_KEY")
            found = False
            for ev in env_var_candidates:
                if os.getenv(ev):
                    print(f"  Env key present: {ev}")
                    found = True
                    break
            if not found:
                print(f"  WARNING: none of {env_var_candidates} are set in environment")

    # --- agents section validation ---
    agents = cfg.get("agents")
    if agents:
        print("\nAgents section found:")
        defaults = agents.get("defaults", {})
        model_section = defaults.get("model", {})
        primary = model_section.get("primary")
        if primary:
            resolved_primary = resolve_placeholders(primary, dotenv)
            # If resolved to an env var placeholder, check env
            if isinstance(resolved_primary, str) and resolved_primary.startswith("${") and resolved_primary.endswith("}"):
                env_name = resolved_primary[2:-1]
                if os.getenv(env_name):
                    print(f"  primary model resolved from env: {env_name}")
                else:
                    print(f"  WARNING: primary model placeholder {resolved_primary} not set in environment")
            else:
                print(f"  primary model: {resolved_primary}")
        else:
            print("  No primary model set in agents.defaults.model")

    print("\nValidation complete.")

if __name__ == '__main__':
    main()
