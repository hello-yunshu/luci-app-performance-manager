// t-asi-no: arrow assignments WITHOUT trailing semicolons
'use strict';
let a, b;
a = () => { return 1; }
b = () => { return 2; }
print(a() + b());
