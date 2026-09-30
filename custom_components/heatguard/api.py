"""RemoteGuard web client with serialized, opt-in commands."""
import asyncio
import aiohttp
from .parser import parse_account, validate

BASE = "https://cp.remoteguard-ivik.com"

class RemoteGuardError(Exception):
    pass

class RemoteGuard:
    def __init__(self, email, password, uid, allow_control=False):
        self.email, self.password, self.uid = email, password, uid
        self.allow_control = allow_control
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self.lock = asyncio.Lock()
        self.logged_in = False

    async def close(self):
        await self.session.close()

    async def _request(self, method, path, **kwargs):
        async with self.session.request(method, BASE + path, **kwargs) as response:
            response.raise_for_status()
            body = await response.text()
            login_page = response.url.path == "/login" or ('name="password"' in body and 'name="email"' in body)
            return body, login_page

    async def _login(self):
        await self._request("GET", "/login")
        _, login_page = await self._request("POST", "/login", data={
            "email": self.email, "password": self.password, "redirect": BASE + "/account"})
        if login_page:
            raise RemoteGuardError("Login failed")
        self.logged_in = True

    async def _account(self):
        if not self.logged_in:
            await self._login()
        html, login_page = await self._request("GET", "/account")
        if login_page:
            self.logged_in = False
            await self._login()
            html, login_page = await self._request("GET", "/account")
        if login_page:
            raise RemoteGuardError("Session expired")
        return parse_account(html, self.uid)

    async def read(self):
        async with self.lock:
            return await self._account()

    async def write(self, changes):
        if not self.allow_control:
            raise RemoteGuardError("Control disabled; enable allow_control after read-only verification")
        if not changes or set(changes) - {"id_59", "id_60", "id_61", "id_62", "target_temperature"}:
            raise RemoteGuardError("Only power, heating/cooling and their setpoints are exposed")
        async with self.lock:
            # The UI sends the entire form: refresh it before every write.
            current = await self._account()
            payload = dict(current["settings"])
            changes = dict(changes)
            if "target_temperature" in changes:
                key = "id_62" if payload["id_60"] == "1" else "id_61"
                changes[key] = changes.pop("target_temperature")
            payload.update({k: str(v) for k, v in changes.items()})
            payload["id_83"] = "0"  # Never replay a latched alarm-reset command.
            validate(payload)
            for key in ("id_61", "id_62", "id_66", "id_67"):
                payload[key] = str(int(float(payload[key])))
            # RemoteGuard rejects unchanged forms with "Нет данных какие нужно изменить!".
            # Compare only requested fields: alarm reset must never trigger a write.
            if all(float(current["settings"][key]) == float(payload[key]) for key in changes):
                return current
            payload["uid"] = self.uid
            import json
            body, login_page = await self._request("POST", "/index.php?route=account/account/setToDevice", data=payload, headers={"X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/account", "Origin": BASE})
            if login_page:
                self.logged_in = False
                raise RemoteGuardError("Session expired during write; command was not retried")
            try:
                result = json.loads(body)
            except (ValueError, TypeError) as err:
                raise RemoteGuardError("Unrecognized write response; command was not retried") from err
            if isinstance(result, dict) and result.get("error") == "Нет данных какие нужно изменить!":
                # Another client may have applied the same command after our read.
                # Accept this specific response only when fresh settings confirm it.
                confirmed = await self._account()
                if all(float(confirmed["settings"][key]) == float(payload[key]) for key in changes):
                    return confirmed
            if not isinstance(result, dict) or result.get("error") or not result.get("success"):
                raise RemoteGuardError("RemoteGuard did not acknowledge command: " + str(result)[:300])
            # A server acknowledgement does not establish that the pump applied it.
            return await self._account()
