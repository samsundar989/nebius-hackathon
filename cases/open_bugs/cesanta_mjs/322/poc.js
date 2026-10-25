let a = [];
for (let i = 0; i < 10; i++) a.push(i);
for (let k in a) { a.splice(0, 1); }
