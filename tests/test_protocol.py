import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'heatguard'
pkg = types.ModuleType('protocol_under_test')
pkg.__path__ = [str(ROOT)]
sys.modules[pkg.__name__] = pkg
try:
    import aiohttp
except ImportError:
    sys.modules['aiohttp'] = types.ModuleType('aiohttp')
from protocol_under_test.parser import parse_account, ParseError, validate
from protocol_under_test.api import RemoteGuard, RemoteGuardError

SETTINGS = {'id_59':'0', 'id_60':'1', 'id_61':'20', 'id_62':'39', 'id_64':'0', 'id_65':'0', 'id_66':'47', 'id_67':'36', 'id_83':'0'}

def fixture(uid='test-device'):
    inputs = ''.join(f'<input type="text" name="{k}" value="{v}">' for k,v in SETTINGS.items() if k != 'id_59')
    return f'''<form class="device_settings">{inputs}<input type="radio" name="id_59" value="1"><input type="radio" name="id_59" value="0" checked><input type="hidden" name="uid" value="{uid}"></form><div id="vals{uid}"><h2>Значення <span class="device-time">(30.09.2026 17:21:23)</span></h2><h5>Температура поточна <span>33.2°С</span></h5><h5>Температура ГВП <span>-40°С</span></h5></div>'''

class ParserTests(unittest.TestCase):
    def test_device_scoping_and_checked_radio(self):
        data = parse_account(fixture('other') + fixture(), 'test-device')
        self.assertEqual(data['settings'], SETTINGS)
        self.assertEqual(data['values']['температура поточна']['value'], 33.2)
        self.assertEqual(data['values']['температура гвп']['value'], -40)
        self.assertEqual(data['device_time'], '30.09.2026 17:21:23')
    def test_missing_device_or_field_fails_closed(self):
        with self.assertRaises(ParseError):
            parse_account(fixture(), 'wrong')
        with self.assertRaises(ParseError):
            parse_account(fixture().replace('name="id_66"', 'name="changed"'), 'test-device')
    def test_limits_nan_and_fractional(self):
        for v in ('56','nan','inf','39.5'):
            with self.assertRaises(ValueError):
                validate({**SETTINGS, 'id_62':v})

class WriteTests(unittest.IsolatedAsyncioTestCase):
    def client(self, settings=None):
        api = RemoteGuard.__new__(RemoteGuard)
        api.allow_control = True
        api.uid = 'test-device'
        api.lock = asyncio.Lock()
        self.sent = []
        async def account():
            return {'settings':dict(settings or SETTINGS)}
        async def request(method, path, **kwargs):
            self.sent.append((method,path,kwargs))
            return '{"success":"queued"}', False
        api._account, api._request = account, request
        return api
    async def test_full_form_preserves_other_values_and_normalizes(self):
        api = self.client({**SETTINGS, 'id_83':'1', 'id_66':'51'})
        await api.write({'target_temperature':'40.0'})
        self.assertEqual(self.sent[0][2]['headers']['X-Requested-With'], 'XMLHttpRequest')
        data = self.sent[0][2]['data']
        self.assertEqual(data['id_62'], '40')
        self.assertEqual(data['id_66'], '51')
        self.assertEqual(data['id_83'], '0')
        self.assertEqual(data['id_59'], '0')
        self.assertEqual(data['uid'], 'test-device')
    async def test_temperature_uses_fresh_mode(self):
        api = self.client({**SETTINGS, 'id_60':'0'})
        await api.write({'target_temperature':'18'})
        self.assertEqual(self.sent[0][2]['data']['id_61'], '18')
        self.assertEqual(self.sent[0][2]['data']['id_62'], '39')
    async def test_readonly_and_unknown_writes_do_not_send(self):
        api = self.client()
        api.allow_control = False
        with self.assertRaises(RemoteGuardError):
            await api.write({'id_59':'1'})
        api.allow_control = True
        with self.assertRaises(RemoteGuardError):
            await api.write({'id_83':'1'})
        self.assertEqual(self.sent, [])
    async def test_unconfirmed_write_is_not_retried(self):
        api = self.client()
        async def request(*args, **kwargs):
            self.sent.append(1)
            return '<html>Login</html>', True
        api._request = request
        with self.assertRaises(RemoteGuardError):
            await api.write({'id_59':'1'})
        self.assertEqual(len(self.sent), 1)
    async def test_invalid_range_does_not_send(self):
        api = self.client()
        with self.assertRaises(ValueError):
            await api.write({'target_temperature':'22'})
        self.assertEqual(self.sent, [])

    async def test_repeated_off_and_equivalent_target_do_not_send(self):
        api = self.client()
        await api.write({'id_59':'0'})
        await api.write({'target_temperature':'39.0'})
        self.assertEqual(self.sent, [])

    async def test_same_mode_with_power_change_still_sends(self):
        api = self.client()
        await api.write({'id_59':'1', 'id_60':'1'})
        self.assertEqual(len(self.sent), 1)

    async def test_no_changes_response_requires_confirmed_settings(self):
        for confirmed in (True, False):
            with self.subTest(confirmed=confirmed):
                api = self.client()
                async def request(*args, **kwargs):
                    self.sent.append(1)
                    if confirmed:
                        async def account():
                            return {'settings':{**SETTINGS, 'id_59':'1'}}
                        api._account = account
                    return '{"error":"Нет данных какие нужно изменить!"}', False
                api._request = request
                if confirmed:
                    await api.write({'id_59':'1'})
                else:
                    with self.assertRaises(RemoteGuardError):
                        await api.write({'id_59':'1'})
                self.assertEqual(len(self.sent), 1)

if __name__ == '__main__':
    unittest.main()
