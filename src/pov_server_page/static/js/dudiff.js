function by_delta(row) {
  return parseInt(row.cells[0].dataset.size);
}
function by_path(row) {
  return row.cells[1].innerText;
}
function sort(key) {
  var table = document.getElementById("du-diff");
  var tbody = table.tBodies[0];
  var rows = tbody.rows;
  var nrows = tbody.rows.length;
  var arr = new Array();
  var i;
  tbody.className = 'sorting';
  for (i = 0; i < nrows; i++) {
    var row = rows[i];
    arr[i] = [key(row), row.outerHTML, i];
  };
  arr.sort(function(a, b) {
    return (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 :
            a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0);
  });
  for (i = 0; i < nrows; i++) {
    arr[i] = arr[i][1];
  }
  tbody.innerHTML = arr.join('');
  tbody.className = '';
}
function limit(depth) {
  var table = document.getElementById("du-diff");
  var i, btn;
  table.className = "du-diff table table-hover limit-" + depth;
  for (i = 1; (btn = document.getElementById('depth-btn-' + i)); i++) {
    if (i == depth) {
      btn.className = "btn btn-primary";
    } else {
      btn.className = "btn btn-default";
    }
  }
}
function limiter(depth) {
  return function() { limit(depth) };
}
function onclick(id, handler) {
  document.getElementById(id).onclick = handler;
}
function init() {
  onclick("sort_by_delta", function() { sort(by_delta) });
  onclick("sort_by_path", function() { sort(by_path) });
  var i, btn;
  for (i = 1; (btn = document.getElementById('depth-btn-' + i)); i++) {
    btn.onclick = limiter(i);
  }
}
init()
