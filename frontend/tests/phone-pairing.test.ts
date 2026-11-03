import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pairingFromURL} from '../lib/phone-pairing';
const code='fixture_'.repeat(7);
test('phone pairing accepts only bounded keys in a private HTTPS fragment',()=>{
 assert.equal(pairingFromURL(`https://mac.fixture.ts.net:8443/#pair=${code}`),code);
 for(const address of [`http://mac.fixture.ts.net:8443/#pair=${code}`,`https://mac.example:8443/#pair=${code}`,`https://mac.fixture.ts.net/#pair=${code}`,`https://mac.fixture.ts.net:8443/?pair=${code}`,'https://mac.fixture.ts.net:8443/#pair=short',`https://mac.fixture.ts.net:8443/#pair=${'x'.repeat(129)}`])assert.equal(pairingFromURL(address),null);
});
