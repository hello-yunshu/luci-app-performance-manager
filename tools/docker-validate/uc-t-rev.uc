// t-rev: caller declared BEFORE callee (forward ref)
function foo() { return bar(); }
function bar() { return 42; }
print(foo());
