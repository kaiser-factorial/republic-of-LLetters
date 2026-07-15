#!/usr/bin/env python3
"""Regression tests for the agent-facing mailbox CLI (no live network/Keychain)."""

from contextlib import nullcontext, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse


DORMITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DORMITORY_ROOT))

import mailbox_cli as cli  # noqa: E402


CONFIG = cli.PublicConfig(
    supabase_url="https://project-ref.supabase.co",
    anon_key="public-anon-key",
    house_email="house@example.com",
    project_ref="project-ref",
)
RESIDENT = {
    "email": "house@example.com",
    "app_metadata": {"dormitory_role": "resident"},
}


class QueueTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, headers, body=None):
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers), "body": body}
        )
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MemoryStore:
    def __init__(self, tokens=None):
        self.tokens = dict(tokens or {})
        self.events = []
        self.fail_save = False

    def load(self, agent):
        self.events.append(("load", agent))
        return self.tokens.get(agent)

    def save(self, agent, token):
        self.events.append(("save", agent, token))
        if self.fail_save:
            raise cli.SessionError("store failed with refresh-secret")
        self.tokens[agent] = token

    def delete(self, agent):
        self.events.append(("delete", agent))
        return self.tokens.pop(agent, None) is not None


class SessionApi:
    def __init__(self):
        self.events = []
        self.refresh_count = 0
        self.refresh_error = None

    def refresh(self, refresh_token):
        self.events.append(("refresh", refresh_token))
        if self.refresh_error:
            raise self.refresh_error
        self.refresh_count += 1
        return cli.AuthSession(
            f"access-{self.refresh_count}",
            f"refresh-{self.refresh_count}",
            RESIDENT,
        )

    def logout_local(self, access_token):
        self.events.append(("logout", access_token))


class CommandApi:
    def __init__(self):
        self.calls = []

    def open_inbox(self, token, actor, recipient, note):
        self.calls.append(("open", token, actor, recipient, note))
        return [
            {
                "id": 7,
                "sender": "Corina",
                "recipient": recipient,
                "subject": "Hello",
                "message": "Checking in",
                "created_at": "2026-07-15T12:00:00Z",
                "reply": None,
                "replied_at": None,
                "published_at": None,
            }
        ]

    def read_ledger(self, token, recipient, limit):
        self.calls.append(("ledger", token, recipient, limit))
        return []

    def send_mail(self, token, actor, recipient, subject, message):
        self.calls.append(("send", token, actor, recipient, subject, message))

    def reply_to_mail(self, token, actor, message_id, reply, publish):
        self.calls.append(("reply", token, actor, message_id, reply, publish))
        return {"id": message_id, "published_at": "now" if publish else None}


class CommandSessions:
    def __init__(self):
        self.calls = []
        self.logged_in = set()

    def has_session(self, agent):
        self.calls.append(("has", agent))
        return agent in self.logged_in

    def login(self, agent, password):
        self.calls.append(("login", agent, password))
        self.logged_in.add(agent)
        return RESIDENT

    def use(self, agent, operation):
        self.calls.append(("use", agent))
        return operation("access-token", RESIDENT)

    def logout(self, agent, forget=False):
        self.calls.append(("logout", agent, forget))
        return self.logged_in.discard(agent) is None


def command_runtime():
    redactor = cli.SecretRedactor()
    api = CommandApi()
    sessions = CommandSessions()
    return cli.Runtime(CONFIG, api, sessions, redactor)


class PublicConfigTests(unittest.TestCase):
    def test_reads_public_config_without_duplicating_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.js"
            path.write_text(
                "\n".join(
                    [
                        "window.SUPABASE_URL = 'https://abc123.supabase.co';",
                        "window.SUPABASE_ANON_KEY = 'anon-value';",
                        "window.DORMITORY_HOUSE_AUTH_EMAIL = 'house@example.com';",
                    ]
                )
            )
            config = cli.load_public_config(path)
        self.assertEqual(config.project_ref, "abc123")
        self.assertEqual(config.house_email, "house@example.com")
        self.assertEqual(config.anon_key, "anon-value")

    def test_agent_allowlist_matches_browser_config(self):
        config = (DORMITORY_ROOT / "config.js").read_text()
        for agent in cli.VALID_AGENTS:
            self.assertRegex(config, rf"\b{agent}:\s*'[A-Z]")
        self.assertNotIn("hermes", cli.VALID_AGENTS)


class SupabaseApiTests(unittest.TestCase):
    def make_api(self, responses):
        redactor = cli.SecretRedactor()
        transport = QueueTransport(responses)
        return cli.SupabaseMailboxApi(CONFIG, redactor, transport), transport, redactor

    def test_password_login_and_resident_verification(self):
        api, transport, redactor = self.make_api(
            [
                {
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "user": RESIDENT,
                },
                RESIDENT,
            ]
        )
        session = api.sign_in("house-password")

        token_call, user_call = transport.calls
        parsed = urlparse(token_call["url"])
        self.assertEqual(token_call["method"], "POST")
        self.assertEqual(parsed.path, "/auth/v1/token")
        self.assertEqual(parse_qs(parsed.query), {"grant_type": ["password"]})
        self.assertEqual(
            token_call["body"],
            {"email": "house@example.com", "password": "house-password"},
        )
        self.assertEqual(user_call["method"], "GET")
        self.assertEqual(urlparse(user_call["url"]).path, "/auth/v1/user")
        self.assertEqual(user_call["headers"]["Authorization"], "Bearer access-secret")
        self.assertEqual(session.refresh_token, "refresh-secret")
        self.assertNotIn("house-password", redactor.clean("house-password access-secret refresh-secret"))

    def test_nonresident_login_is_rejected_and_locally_logged_out(self):
        nonresident = {"app_metadata": {}}
        api, transport, _redactor = self.make_api(
            [
                {
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "user": nonresident,
                },
                nonresident,
                None,
            ]
        )
        with self.assertRaises(cli.SessionError):
            api.sign_in("house-password")
        logout_call = transport.calls[-1]
        parsed = urlparse(logout_call["url"])
        self.assertEqual(parsed.path, "/auth/v1/logout")
        self.assertEqual(parse_qs(parsed.query), {"scope": ["local"]})

    def test_refresh_open_ledger_send_and_reply_request_shapes(self):
        api, transport, _redactor = self.make_api(
            [
                {
                    "access_token": "fresh-access",
                    "refresh_token": "rotated-refresh",
                    "user": RESIDENT,
                },
                [],
                [],
                None,
                {"id": 9, "published_at": None},
            ]
        )
        session = api.refresh("old-refresh")
        api.open_inbox(session.access_token, "codex", "codex", "Checking via CLI")
        api.read_ledger(session.access_token, "codex", 25)
        api.send_mail(
            session.access_token,
            "codex",
            "avery",
            "Handoff",
            "A private note",
        )
        api.reply_to_mail(session.access_token, "codex", 9, "A reply", False)

        refresh_call, open_call, ledger_call, send_call, reply_call = transport.calls
        self.assertEqual(
            parse_qs(urlparse(refresh_call["url"]).query),
            {"grant_type": ["refresh_token"]},
        )
        self.assertEqual(refresh_call["body"], {"refresh_token": "old-refresh"})
        self.assertEqual(urlparse(open_call["url"]).path, "/rest/v1/rpc/open_inbox")
        self.assertEqual(
            open_call["body"],
            {
                "p_claimed_actor": "codex",
                "p_target_recipient": "codex",
                "p_access_note": "Checking via CLI",
            },
        )
        ledger_query = parse_qs(urlparse(ledger_call["url"]).query)
        self.assertEqual(ledger_query["target_recipient"], ["eq.codex"])
        self.assertEqual(ledger_query["order"], ["occurred_at.desc"])
        self.assertEqual(ledger_query["limit"], ["25"])
        self.assertEqual(urlparse(send_call["url"]).path, "/rest/v1/mailboxes")
        self.assertEqual(send_call["method"], "POST")
        self.assertEqual(send_call["headers"]["Authorization"], "Bearer fresh-access")
        self.assertEqual(send_call["headers"]["Prefer"], "return=minimal")
        self.assertEqual(
            send_call["body"],
            {
                "sender": "Codex",
                "recipient": "avery",
                "subject": "Handoff",
                "message": "A private note",
            },
        )
        self.assertEqual(urlparse(reply_call["url"]).path, "/rest/v1/rpc/reply_to_mail")
        self.assertEqual(
            reply_call["body"],
            {
                "p_claimed_actor": "codex",
                "p_message_id": 9,
                "p_reply": "A reply",
                "p_publish": False,
            },
        )

    def test_send_network_failure_reports_unknown_delivery_without_retry(self):
        api, transport, _redactor = self.make_api(
            [cli.MailboxCliError("Could not reach the dormitory mailbox service")]
        )
        with self.assertRaisesRegex(cli.MailboxCliError, "delivery status is unknown"):
            api.send_mail("access-token", "codex", "avery", "Hello", "Private body")
        self.assertEqual(len(transport.calls), 1)

    def test_send_api_error_preserves_status_without_echoing_letter_content(self):
        api, transport, redactor = self.make_api(
            [cli.ApiError(400, "Handoff: Private body was rejected")]
        )
        with self.assertRaises(cli.ApiError) as raised:
            api.send_mail("access-token", "codex", "avery", "Handoff", "Private body")
        self.assertEqual(raised.exception.status, 400)
        self.assertEqual(str(raised.exception), "The mailbox service rejected this letter")
        self.assertNotIn("Handoff", redactor.clean(raised.exception))
        self.assertNotIn("Private body", redactor.clean(raised.exception))
        self.assertEqual(len(transport.calls), 1)

    def test_send_server_error_is_unknown_and_not_retried(self):
        api, transport, _redactor = self.make_api(
            [cli.ApiError(503, "upstream unavailable after insert")]
        )
        with self.assertRaisesRegex(cli.MailboxCliError, "delivery status is unknown"):
            api.send_mail("access-token", "codex", "avery", "Hello", "Private body")
        self.assertEqual(len(transport.calls), 1)


class KeychainStoreTests(unittest.TestCase):
    def make_store(self, runner):
        patcher = mock.patch.object(cli.platform, "system", return_value="Darwin")
        patcher.start()
        self.addCleanup(patcher.stop)
        return cli.MacKeychainSessionStore(
            "project-ref",
            cli.SecretRedactor(),
            runner=runner,
            security_path="/usr/bin/true",
        )

    def test_keychain_write_uses_stdin_hex_not_secret_argv(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

        store = self.make_store(runner)
        store.save("codex", "refresh-secret")
        args, kwargs = calls[0]
        self.assertEqual(args, ["/usr/bin/true", "-q", "-i"])
        self.assertNotIn("refresh-secret", " ".join(args))
        self.assertNotIn(b"refresh-secret", kwargs["input"])
        self.assertIn(b"726566726573682d736563726574", kwargs["input"])
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertFalse(kwargs["shell"])

    def test_keychain_os_error_is_redacted_session_failure(self):
        def runner(_args, **_kwargs):
            raise OSError("runner failed with refresh-secret")

        store = self.make_store(runner)
        with self.assertRaisesRegex(cli.SessionError, "Could not access macOS Keychain"):
            store.save("codex", "refresh-secret")

    def test_keychain_load_removes_one_newline_and_accounts_are_distinct(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout=b"refresh-token\n", stderr=b"")

        store = self.make_store(runner)
        self.assertEqual(store.load("codex"), "refresh-token")
        store.load("avery")
        self.assertIn("project-ref:codex", calls[0])
        self.assertIn("project-ref:avery", calls[1])

    def test_missing_keychain_item_is_none_and_delete_is_idempotent(self):
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 44, stdout=b"", stderr=b"not found")

        store = self.make_store(runner)
        self.assertIsNone(store.load("codex"))
        self.assertFalse(store.delete("codex"))


class SessionManagerTests(unittest.TestCase):
    @staticmethod
    def manager(api, store):
        return cli.SessionManager(api, store, lock_factory=lambda _agent: nullcontext())

    def test_rotated_refresh_token_is_saved_before_operation(self):
        api = SessionApi()
        store = MemoryStore({"codex": "refresh-old"})
        manager = self.manager(api, store)
        events = []

        def operation(access_token, _user):
            events.extend(store.events)
            events.append(("operation", access_token))
            return "mail"

        self.assertEqual(manager.use("codex", operation), "mail")
        self.assertIn(("save", "codex", "refresh-1"), events)
        self.assertLess(
            events.index(("save", "codex", "refresh-1")),
            events.index(("operation", "access-1")),
        )

    def test_401_refreshes_and_replays_exactly_once(self):
        api = SessionApi()
        store = MemoryStore({"codex": "refresh-old"})
        manager = self.manager(api, store)
        attempts = []

        def operation(access_token, _user):
            attempts.append(access_token)
            if len(attempts) == 1:
                raise cli.ApiError(401, "expired")
            return "ok"

        self.assertEqual(manager.use("codex", operation), "ok")
        self.assertEqual(attempts, ["access-1", "access-2"])
        self.assertEqual(api.refresh_count, 2)

    def test_invalid_refresh_clears_stale_session(self):
        api = SessionApi()
        api.refresh_error = cli.ApiError(401, "invalid refresh-secret")
        store = MemoryStore({"codex": "refresh-secret"})
        manager = self.manager(api, store)
        with self.assertRaises(cli.SessionError):
            manager.use("codex", lambda _token, _user: None)
        self.assertNotIn("codex", store.tokens)

    def test_storage_failure_prevents_mailbox_operation(self):
        api = SessionApi()
        store = MemoryStore({"codex": "refresh-old"})
        store.fail_save = True
        manager = self.manager(api, store)
        called = False

        def operation(_token, _user):
            nonlocal called
            called = True

        with self.assertRaises(cli.SessionError):
            manager.use("codex", operation)
        self.assertFalse(called)
        self.assertIn(("logout", "access-1"), api.events)

    def test_forget_deletes_without_loading_an_unreadable_token(self):
        class UnreadableStore:
            def __init__(self):
                self.deleted = False

            def load(self, _agent):
                raise AssertionError("--forget must not read the saved token")

            def delete(self, agent):
                self.deleted = agent == "codex"
                return True

        store = UnreadableStore()
        manager = self.manager(SessionApi(), store)
        self.assertTrue(manager.logout("codex", forget=True))
        self.assertTrue(store.deleted)


class CommandContractTests(unittest.TestCase):
    def setUp(self):
        self.parser = cli.build_parser()

    def test_open_defaults_to_own_inbox_and_audited_note(self):
        runtime = command_runtime()
        args = self.parser.parse_args(["open", "--as", "codex"])
        payload, lines = cli.execute(args, runtime)
        self.assertEqual(payload["recipient"], "codex")
        self.assertFalse(payload["cross_room"])
        self.assertTrue(payload["access_logged"])
        self.assertEqual(
            runtime.api.calls[0],
            ("open", "access-token", "codex", "codex", cli.DEFAULT_ACCESS_NOTE),
        )
        self.assertIn("access recorded", lines[0])

    def test_cross_room_requires_override_and_explicit_note_before_auth(self):
        runtime = command_runtime()
        args = self.parser.parse_args(["open", "--as", "codex", "--inbox", "avery"])
        with self.assertRaises(cli.ValidationError):
            cli.execute(args, runtime)
        self.assertNotIn(("use", "codex"), runtime.sessions.calls)

        args = self.parser.parse_args(
            [
                "open",
                "--as",
                "codex",
                "--inbox",
                "avery",
                "--allow-cross-room",
                "--note",
                "Checking Avery's inbox for a handoff",
            ]
        )
        payload, _lines = cli.execute(args, runtime)
        self.assertTrue(payload["cross_room"])
        self.assertEqual(runtime.api.calls[-1][3], "avery")

    def test_post_reply_is_public_and_draft_is_resident_only(self):
        runtime = command_runtime()
        args = self.parser.parse_args(
            [
                "post-reply",
                "7",
                "--as",
                "codex",
                "--text",
                "A visible reply",
            ]
        )
        payload, lines = cli.execute(args, runtime)
        self.assertTrue(payload["published"])
        self.assertEqual(
            runtime.api.calls[-1],
            ("reply", "access-token", "codex", 7, "A visible reply", True),
        )
        self.assertIn("posted publicly", lines[0])
        self.assertIn("everyone can see", lines[0])

        args = self.parser.parse_args(
            ["draft", "7", "--as", "codex", "--text", "A working draft"]
        )
        payload, lines = cli.execute(args, runtime)
        self.assertFalse(payload["published"])
        self.assertEqual(
            runtime.api.calls[-1],
            ("reply", "access-token", "codex", 7, "A working draft", False),
        )
        self.assertIn("sender cannot see it", lines[0])

    def test_send_from_stdin_uses_agent_session_and_omits_private_content_from_output(self):
        runtime = command_runtime()
        private_body = "First private line\nsecond private line"
        args = self.parser.parse_args(
            [
                "send",
                "--as",
                "codex",
                "--to",
                "avery",
                "--subject",
                "Handoff",
                "--file",
                "-",
            ]
        )
        payload, lines = cli.execute(
            args,
            runtime,
            stdin=io.StringIO(f"  {private_body}\n"),
        )

        self.assertEqual(runtime.sessions.calls, [("use", "codex")])
        self.assertEqual(
            runtime.api.calls,
            [
                (
                    "send",
                    "access-token",
                    "codex",
                    "avery",
                    "Handoff",
                    private_body,
                )
            ],
        )
        self.assertEqual(
            payload,
            {
                "command": "send",
                "actor": "codex",
                "recipient": "avery",
                "message_length": len(private_body),
                "delivered": True,
                "sender_verified": False,
                "access_ledger_entry_created": False,
            },
        )
        rendered = "\n".join(lines) + json.dumps(payload)
        self.assertNotIn(private_body, rendered)
        self.assertNotIn("Handoff", rendered)
        self.assertIn("Delivered a private letter to Avery", lines[0])
        self.assertIn("self-declared sender label", lines[0])
        self.assertIn("no access-ledger entry was created", lines[0])

    def test_send_validates_irreversible_insert_before_auth(self):
        invalid_cases = [
            ["--subject", "   ", "--text", "body"],
            ["--subject", "x" * 161, "--text", "body"],
            ["--subject", "line one\nline two", "--text", "body"],
            ["--subject", "spoof\u202etxt", "--text", "body"],
            ["--subject", "Hello", "--text", "   "],
            ["--subject", "Hello", "--text", "x" * 5001],
            ["--subject", "Hello", "--file", "/definitely/missing/private-note.txt"],
        ]
        for tail in invalid_cases:
            with self.subTest(tail=tail):
                runtime = command_runtime()
                args = self.parser.parse_args(
                    ["send", "--as", "codex", "--to", "avery", *tail]
                )
                with self.assertRaises(cli.ValidationError):
                    cli.execute(args, runtime)
                self.assertEqual(runtime.sessions.calls, [])

    def test_send_rejects_public_or_spoofable_recipient_surface(self):
        for recipient in ("common", "hermes"):
            with self.subTest(recipient=recipient):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    self.parser.parse_args(
                        [
                            "send",
                            "--as",
                            "codex",
                            "--to",
                            recipient,
                            "--subject",
                            "Hello",
                            "--text",
                            "body",
                        ]
                    )

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(
                [
                    "send",
                    "--as",
                    "codex",
                    "--to",
                    "avery",
                    "--from",
                    "laguna",
                    "--subject",
                    "Hello",
                    "--text",
                    "body",
                ]
            )

    def test_legacy_reply_command_is_rejected(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(
                ["reply", "7", "--as", "codex", "--text", "ambiguous"]
            )

    def test_unknown_legacy_agent_is_rejected_by_parser(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            self.parser.parse_args(["open", "--as", "hermes"])

    def test_json_output_is_one_document_and_error_is_redacted(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            cli._emit_success({"command": "ledger", "entries": []}, [], True)
        self.assertEqual(json.loads(stdout.getvalue()), {"ok": True, "command": "ledger", "entries": []})

        redactor = cli.SecretRedactor()
        redactor.add("refresh-secret")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            cli._emit_error(cli.SessionError("bad refresh-secret"), redactor, True)
        error_payload = json.loads(stderr.getvalue())
        self.assertFalse(error_payload["ok"])
        self.assertNotIn("refresh-secret", error_payload["error"])

    def test_noninteractive_house_key_prompt_fails_closed(self):
        with mock.patch.object(cli.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(cli.ValidationError, "interactive terminal"):
                cli.prompt_house_key("House key: ")

    def test_human_output_neutralizes_terminal_controls(self):
        message = {
            "id": 7,
            "sender": "Visitor\x1b]52;clipboard\x07",
            "created_at": "now\rspoofed",
            "subject": "Hello\nFake header",
            "message": "line one\nline two\x1b[2J\u202espoof",
            "reply": None,
        }
        rendered = "\n".join(cli._human_message(message))
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\x07", rendered)
        self.assertNotIn("\r", rendered)
        self.assertNotIn("\u202e", rendered)
        self.assertIn("\\x1b", rendered)
        self.assertIn("\\u202e", rendered)
        self.assertIn("Hello\\nFake header", rendered)


if __name__ == "__main__":
    unittest.main()
