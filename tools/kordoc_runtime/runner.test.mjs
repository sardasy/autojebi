import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
const execute = (script, permission = true) => spawnSync(process.execPath,
  [...(permission ? ['--permission', `--allow-fs-read=${root}`] : []), '--input-type=module', '-e', script],
  {cwd: root, encoding: 'utf8', timeout: 10000});

test('guard requires restricted Node permissions', () => {
  const result = execute("import {lockDown} from './guard.mjs'; lockDown();", false);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /permission_required/);
});

test('guard denies COM launch, network and source writes', () => {
  const result = execute(`
    import {lockDown} from './guard.mjs';
    import {execFileSync} from 'node:child_process';
    import {writeFileSync,readFileSync} from 'node:fs';
    import {request} from 'node:https';
    import {connect} from 'node:net';
    import assert from 'node:assert/strict';
    lockDown();
    for (const operation of [() => execFileSync('powershell', []),
      () => request('https://example.com'), () => fetch('https://example.com'),
      () => connect(443,'example.com')]) assert.throws(operation, /external_operation_blocked/);
    assert.throws(() => writeFileSync('./must-not-exist.txt', 'x'), /Access to this API has been restricted/);
    assert.throws(() => readFileSync('../package.json'), /Access to this API has been restricted/);
  `);
  assert.equal(result.status, 0, result.stderr);
});
