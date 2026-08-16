#!/usr/bin/env ucode
'use strict';

/* Mirrors the REORDERED production source: callee defined BEFORE caller
 * (no forward references — verified 0 in the shipped Core). */
function helper(x) {
	return x * 2;
}

function caller() {
	return helper(21);
}

function seam() {
	return 'original';
}

function use_seam() {
	return seam();
}

/* The harness re-seats data-provider seams after the library loads.  This must
 * be visible to already-defined callers (ucode resolves bindings at
 * definition time, so seams must already be declared — they are). */
let r0 = caller();
helper = function(x) { return x * 100; };
let r1 = caller();
print('caller-before=' + r0 + ' caller-after-reassign=' + r1 + '\n');
if (r0 != 42) { print('FAIL: expected 42, got ' + r0 + '\n'); exit(1); }
if (r1 != 2100) { print('FAIL: expected 2100 after reassign, got ' + r1 + '\n'); exit(1); }

let s0 = use_seam();
seam = function() { return 'replaced'; };
let s1 = use_seam();
print('seam-before=' + s0 + ' seam-after=' + s1 + '\n');
if (s0 != 'original' || s1 != 'replaced') { print('FAIL: seam re-seat failed\n'); exit(1); }

print('FN-REASSIGN-OK\n');
exit(0);
