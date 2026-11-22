"""Run three real-model checks with python3 -B live_test.py."""
import json
import os
import sys
from http.client import IncompleteRead
from config import read_env, unquote
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from agents import answer, collect_evidence, verify
from model_errors import ModelRequestError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def load_model():
    settings = read_env()
    names = ("LLM_ENDPOINT", "LLM_MODEL", "LLM_API_KEY")
    endpoint, model_name, key = (unquote(os.environ.get(name, settings.get(name, ""))) for name in names)
    if not all((endpoint, model_name, key)):
        raise SystemExit("Set LLM_ENDPOINT, LLM_MODEL and LLM_API_KEY in your local .env first.")
    url = urlsplit(endpoint)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise SystemExit("LLM_ENDPOINT must be an HTTPS URL without embedded credentials.")
    opener = build_opener(NoRedirect())

    def model(system, payload):
        body = json.dumps({"model": model_name, "response_format": {"type": "json_object"},
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]})
        request = Request(endpoint, data=body.encode(), headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + key})
        try:
            with opener.open(request, timeout=40) as response:
                try:
                    raw = response.read()
                except IncompleteRead as exc:
                    # Some gateways close after sending the complete JSON body.
                    raw = exc.partial
                result = json.loads(raw)
            parsed = json.loads(result["choices"][0]["message"]["content"])
            if not isinstance(parsed, dict):
                raise ValueError("Expected JSON object")
        except HTTPError as exc:
            raise ModelRequestError(exc.code) from None
        except (URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
            raise RuntimeError("Model request failed or response was not a JSON object.") from None
        usage = result.get("usage") or {}
        print("Tokens:", {name: usage[name] for name in
                          ("prompt_tokens", "completion_tokens", "total_tokens") if name in usage}, file=sys.stderr)
        return parsed

    return model


def main():
    model = load_model()
    evidence = collect_evidence(schedule=[
        {"evidence_id": "schedule:test-1", "text": "COMP5926 class starts at 14:00.",
         "citation": {"title": "Synthetic class schedule"}}])
    question = "What time does the COMP5926 class start?"
    draft = answer(question, evidence, model)
    normal = verify(question, evidence, draft, model)
    wrong = {"claims": [{"text": "The COMP5926 class starts at 15:00.", "supports": [
        {"evidence_id": "schedule:test-1", "quote": "COMP5926 class starts at 14:00."}]}]}
    contradiction = verify(question, evidence, wrong, model)
    missing = verify(question + " What is the room?", evidence, draft, model)
    cases = {"normal": (normal, "passed"), "wrong_time": (contradiction, "rejected"),
             "missing_room": (missing, "insufficient_evidence")}
    success = True
    for name, (result, expected) in cases.items():
        matched = result["status"] == expected
        print(name, "PASS" if matched else "FAIL", result["status"], result.get("issues", []),
              result.get("unanswered", []))
        success &= matched
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
