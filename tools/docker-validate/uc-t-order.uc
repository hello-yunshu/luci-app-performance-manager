// t-order: callee declared BEFORE caller
function bar() { return 42; }
function foo() { return bar(); }
print(foo());
