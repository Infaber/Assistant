import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseActivity, updateActivity, finishActivity, type Activity } from '../lib/activity';
const event: Activity = { version:1, id:'one', kind:'action', label:'Safari', detail:'Working', timestamp:100, status:'running' };
const bytes = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));

test('accepts bounded activity and strips extra fields', () => {
  assert.deepEqual(parseActivity(bytes({...event, secret:'never render'})),event);
  for (const bad of [null, {}, {...event, status:'success'}, {...event, detail:'x'.repeat(501)}, {...event, timestamp:'now'}, {...event, id:''}]) assert.equal(parseActivity(bytes(bad)),null);
  assert.equal(parseActivity(new Uint8Array(5000)),null);
});
test('out of order starts never replace terminal results', () => {
  const done: Activity = {...event, timestamp:102, status:'verified'};
  assert.deepEqual(updateActivity([done],event),[done]);
  assert.deepEqual(updateActivity([done],{...event,timestamp:103}),[done]);
  assert.deepEqual(updateActivity([event],done),[done]);
});
test('bounds retained events and marks disconnected actions uncertain', () => {
  let rows: Activity[]=[];
  for(let i=0;i<50;i++) rows=updateActivity(rows,{...event,id:String(i)});
  assert.equal(rows.length,40); assert.equal(rows[0].id,'10');
  assert.equal(finishActivity(rows)[0].status,'uncertain');
  assert.equal(finishActivity([{...event,status:'verified'}])[0].status,'verified');
});
