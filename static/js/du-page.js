var map = document.getElementById('map');
appendTreemap(map, tree);
var footer = document.getElementById('footer');
footer.innerHTML = 'Last updated on ' + last_updated + '.  Disk usage computed in ' + duration + ' seconds.';
