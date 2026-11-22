"""One minimal synthetic JSON request using local model settings; no secrets logged."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.settings import read_settings, configuration_issues
from app.pipeline_engine import _model_factory


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    settings = read_settings()
    issues = configuration_issues(settings)
    if issues:
        for issue in issues:
            print(issue)
        return 1
    try:
        model, usage = _model_factory(settings)
        result = model('Return only a JSON object: {"ok": true}.', {"test": "connection"})
    except Exception as exc:
        from model_errors import ModelRequestError
        print(str(exc) if isinstance(exc, ModelRequestError) else f"Model connection failed ({type(exc).__name__})")
        return 1
    print("JSON response valid:", result.get("ok") is True)
    print("Usage:", usage)
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
