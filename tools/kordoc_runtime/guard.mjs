import child from 'node:child_process';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import tls from 'node:tls';
import dgram from 'node:dgram';
import dns from 'node:dns';
import { syncBuiltinESMExports } from 'node:module';

export function lockDown() {
  if (!process.permission || process.permission.has('child') ||
      process.permission.has('worker') || process.permission.has('addons') ||
      process.permission.has('fs.write')) throw new Error('permission_required');
  const deny = () => { throw new Error('external_operation_blocked'); };
  for (const name of ['exec', 'execFile', 'execSync', 'execFileSync', 'spawn', 'spawnSync', 'fork']) child[name] = deny;
  for (const module of [http, https]) { module.request = deny; module.get = deny; module.createServer = deny; }
  net.connect = net.createConnection = net.createServer = deny;
  net.Socket.prototype.connect = deny;
  tls.connect = tls.createServer = deny;
  dgram.createSocket = deny;
  for (const name of Object.keys(dns)) if (/^(lookup|resolve)/.test(name)) dns[name] = deny;
  for (const name of Object.keys(dns.promises)) if (/^(lookup|resolve)/.test(name)) dns.promises[name] = deny;
  globalThis.fetch = deny;
  globalThis.WebSocket = class { constructor() { deny(); } };
  process.env.KORDOC_OFFLINE = '1';
  syncBuiltinESMExports();
}
