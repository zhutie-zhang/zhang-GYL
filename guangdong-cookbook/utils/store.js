(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) module.exports = factory();
  else root.STORE = factory();
})(this, function () {
  function mem() { return {}; }
  var cache = mem();

  function hasWx() { return typeof wx !== 'undefined' && wx.getStorageSync; }
  function hasLocal() { return typeof window !== 'undefined' && window.localStorage; }

  function get(key, def) {
    try {
      if (hasWx()) {
        var v = wx.getStorageSync(key);
        return (v === '' || v === undefined || v === null) ? def : v;
      }
      if (hasLocal()) {
        var s = window.localStorage.getItem('gdcb_' + key);
        if (s === null || s === undefined) return def;
        return JSON.parse(s);
      }
    } catch (e) {}
    return (key in cache) ? cache[key] : def;
  }
  function set(key, val) {
    cache[key] = val;
    try {
      if (hasWx()) wx.setStorageSync(key, val);
      if (hasLocal()) window.localStorage.setItem('gdcb_' + key, JSON.stringify(val));
    } catch (e) {}
  }

  var DEFAULTS = {
    profile: 'normal',
    family: 3,
    taste: 'light',          // light 清淡 | spicy 微辣
    veto: [],                // beef | seafood | organ | preserved | veg
    recentDishes: []
  };

  function getPrefs() {
    var p = get('prefs', null);
    return Object.assign({}, DEFAULTS, p || {});
  }
  function savePrefs(p) { set('prefs', p); }
  function menuSeed() { return get('menuSeed', '0'); }
  function setMenuSeed(s) { set('menuSeed', s); }

  function listRecords() { return get('records', []); }
  function saveRecord(r) {
    var list = listRecords();
    var idx = -1;
    list.forEach(function (x, i) { if (x.date === r.date) idx = i; });
    if (idx >= 0) list[idx] = r; else list.push(r);
    list.sort(function (a, b) { return a.date < b.date ? 1 : -1; });
    if (list.length > 60) list = list.slice(0, 60);
    set('records', list);
    return list;
  }
  function removeRecord(date) {
    var list = listRecords().filter(function (x) { return x.date !== date; });
    set('records', list);
    return list;
  }

  return {
    get: get,
    set: set,
    prefs: getPrefs,
    savePrefs: savePrefs,
    menuSeed: menuSeed,
    setMenuSeed: setMenuSeed,
    listRecords: listRecords,
    saveRecord: saveRecord,
    removeRecord: removeRecord
  };
});