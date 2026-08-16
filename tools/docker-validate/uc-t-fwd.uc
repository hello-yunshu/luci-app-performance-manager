/* Empirically test whether ucode supports `function name;` forward declaration. */
function later;

function first() {
	/* call a function defined later in source */
	return later() + 1;
}

function later() {
	return 41;
}

print('first() = ', first(), '\n');
