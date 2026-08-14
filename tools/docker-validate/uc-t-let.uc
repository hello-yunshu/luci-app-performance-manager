// t-let: let + arrow with forward reference
'use strict';
let foo, bar;
foo = () => { return bar(); };
bar = () => { return 42; };
print(foo());
