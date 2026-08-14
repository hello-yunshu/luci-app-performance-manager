// t-dup: same local var name in two arrow functions
'use strict';
let a, b;
a = () => { let p = 1; return p; };
b = () => { let p = 2; return p; };
print(a() + b());
