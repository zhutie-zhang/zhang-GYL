(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) module.exports = factory(require('./guide'), require('./recipes'), require('./nutrition'));
  else root.RECOMMEND = factory(root.GUIDE, root.RECIPES, root.NUTRITION);
})(this, function (GUIDE, RECIPES, NUTRITION) {

  var HCLASS = {
    baqieji: '禽', yanjuji: '禽', chashao: '畜', chizhi: '畜', kejianiang: '蛋豆',
    qingzhengluyu: '水产', baizhuojiweixia: '水产', huadanxiaren: '水产',
    fanqieniurou: '畜', qingjiaoniurou: '畜', xianggu_sj: '禽', gulurou: '畜'
  };

  var POOLS = {
    bfastMain: ['pidanzd', 'shengyu', 'tingzaizhou', 'baizhou', 'rou_changfen', 'zhai_changfen', 'nuomiji', 'chiyouhcm', 'laweibaozai'],
    bfastSide: ['xianxiajiao', 'magao', 'jiucaichaodan', 'baizhuocaixin', 'suanxilan', 'liangguajd', 'shangtang_ww', 'yaozhuzd'],
    herbs: ['baqieji', 'yanjuji', 'chashao', 'chizhi', 'qingzhengluyu', 'baizhuojiweixia', 'huadanxiaren', 'fanqieniurou', 'qingjiaoniurou', 'xianggu_sj', 'gulurou', 'kejianiang'],
    vegies: ['baizhuocaixin', 'suanjielan', 'haoyoushengcai', 'shangtang_ww', 'douchilingyu', 'suanxilan', 'jiucaichaodan', 'liangguajd', 'qingzheng_doufu'],
    lightSoup: ['fanqiedht', 'zicaixiapi', 'doufuyoutou', 'dongguahaidai'],
    richSoup: ['dongguayiyimi', 'lianouhs', 'hongluobo', 'xiyangcai', 'wuzhimaotao']
  };
  var POOL_IDS = {};
  Object.keys(POOLS).forEach(function (k) {
    POOLS[k].forEach(function (id) { POOL_IDS[id] = 1; });
  });

  var SENIOR_HERBS = ['qingzhengluyu', 'baizhuojiweixia', 'huadanxiaren', 'baqieji', 'xianggu_sj', 'kejianiang', 'chizhi'];
  var SENIOR_BFAST = ['pidanzd', 'shengyu', 'baizhou', 'rou_changfen', 'ming_zhou_tou'];

  function hashStr(s) {
    var h = 2166136261;
    for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function weekDay(d) {
    return ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
  }
  function dateStr(d) {
    return d.getFullYear() + '-' + (d.getMonth() + 1 < 10 ? '0' : '') + (d.getMonth() + 1) + '-' + (d.getDate() < 10 ? '0' : '') + d.getDate();
  }

  function ok(r, prefs) {
    if (!r) return false;
    var v = prefs.veto || [];
    for (var i = 0; i < v.length; i++) {
      if (r.veto && r.veto.indexOf(v[i]) >= 0) return false;
    }
    if (v.indexOf('veg') >= 0 && !r.veg) return false;
    return true;
  }

  function pick(pool, rnd, used, extraFilter) {
    var avail = pool.filter(function (id) {
      var r = RECIPES.byId[id];
      if (!ok(r, used.prefs)) return false;
      if (used.ids[id]) return false;
      if (extraFilter && !extraFilter(r)) return false;
      return true;
    });
    if (!avail.length) return null;
    var fresh = avail.filter(function (id) { return used.recent.indexOf(id) < 0; });
    var src = fresh.length ? fresh : avail;
    return src[Math.floor(rnd() * src.length)];
  }

  function build(seed, prefs) {
    prefs = prefs || {};
    prefs.profile = prefs.profile || 'normal';
    prefs.family = Math.max(1, prefs.family || 1);
    prefs.taste = prefs.taste || 'light';
    prefs.veto = prefs.veto || [];
    prefs.recentDishes = prefs.recentDishes || [];
    var rnd = mulberry32(seed);
    var used = { ids: {}, recent: prefs.recentDishes, prefs: prefs };
    function mark(id) { if (id) used.ids[id] = 1; }

    var herbsPool = POOLS.herbs.slice();
    var bfastPool = POOLS.bfastMain.slice();
    if (prefs.profile === 'diet') {
      herbsPool = herbsPool.filter(function (id) {
        var r = RECIPES.byId[id]; return r && !r.occa && r.nutrition.kcal <= 330;
      });
    } else if (prefs.profile === 'senior') {
      herbsPool = SENIOR_HERBS.filter(function (id) { return POOL_IDS[id]; });
      bfastPool = SENIOR_BFAST.filter(function (id) { return POOL_IDS[id]; });
    }

    // 早餐
    var bMain = pick(bfastPool, rnd, used);
    mark(bMain);
    var bSide = pick(POOLS.bfastSide, rnd, used);
    mark(bSide);

    // 午餐
    var lSoup = pick(POOLS.lightSoup, rnd, used); mark(lSoup);
    var lHerb = null;
    if (used.prefs.veto.indexOf('veg') < 0) { lHerb = pick(herbsPool, rnd, used); mark(lHerb); }
    var lVeg = pick(POOLS.vegies, rnd, used); mark(lVeg);
    var lRice = prefs.profile === 'diet' ? 'zaliangfan' : 'hongshu_or_fan';

    // 晚餐
    var dSoup = pick(POOLS.richSoup, rnd, used); mark(dSoup);
    var dHerb = null;
    if (used.prefs.veto.indexOf('veg') < 0) {
      var lClass = lHerb ? HCLASS[lHerb] : null;
      dHerb = pick(herbsPool, rnd, used, lClass ? function (r) { return HCLASS[r.id] !== lClass; } : null);
      mark(dHerb);
    }
    var dVeg = pick(POOLS.vegies, rnd, used); mark(dVeg);
    var dRice = prefs.profile === 'diet' ? 'zaliangfan' : 'fan';

    function dishOf(id, role) {
      var r = RECIPES.byId[id];
      if (!r) return null;
      return {
        id: r.id, name: r.name, kind: r.kind, group: r.group, role: role,
        kcal: r.nutrition.kcal, nutrition: r.nutrition, tags: r.tags,
        occa: !!r.occa, tip: r.tip, ingredients: r.ingredients, item: false
      };
    }

    var milk = {
      item: true, id: 'milk', name: '牛奶（低脂）300ml', role: '奶制品', group: '奶类', kcal: 130,
      nutrition: { kcal: 130, protein: 10, fat: 3, carb: 12, fiber: 0, sodium: 100, vegGram: 0 },
      ingredients: [{ n: '低脂牛奶', g: 300, gr: '奶' }],
      note: '膳食指南建议每天奶及奶制品 300~500 克',
      tags: ['补钙']
    };
    var fruit = {
      item: true, id: 'fruit', name: '时令水果 200g', role: '水果', group: '水果', kcal: 100,
      nutrition: { kcal: 100, protein: 1, fat: 0, carb: 25, fiber: 4, sodium: 5, vegGram: 200 },
      ingredients: [{ n: '时令水果', g: 200, gr: '果' }],
      note: '水果 200~350 克/天，两餐之间吃更佳',
      tags: ['维生素'], veto: [], veg: true
    };

    var meals = [
      { key: 'breakfast', name: '早餐', tip: '多储蛋白质，配奶豆更佳', dishes: [] },
      { key: 'lunch', name: '午餐', tip: '荤素搭配，汤鲜开胃', dishes: [] },
      { key: 'dinner', name: '晚餐', tip: '老火靓汤，清淡收尾', dishes: [] },
      { key: 'snack', name: '加餐', tip: '奶豆水果妙不可少', dishes: [] }
    ];
    if (bMain) meals[0].dishes.push(dishOf(bMain, '主食'));
    if (bSide) meals[0].dishes.push(dishOf(bSide, '配菜'));
    if (lSoup) meals[1].dishes.push(dishOf(lSoup, '汤'));
    if (lHerb) meals[1].dishes.push(dishOf(lHerb, '荤菜'));
    if (lVeg) meals[1].dishes.push(dishOf(lVeg, '素菜'));
    if (lRice === 'hongshu_or_fan') {
      meals[1].dishes.push(Object.assign(dishOf('fan', '主食'), { substitute: '可用杂粮饭或蒸红薯替代' }));
    } else {
      meals[1].dishes.push(dishOf('zaliangfan', '主食'));
    }
    if (dSoup) meals[2].dishes.push(dishOf(dSoup, '汤'));
    if (dHerb) meals[2].dishes.push(dishOf(dHerb, '荤菜'));
    if (dVeg) meals[2].dishes.push(dishOf(dVeg, '素菜'));
    meals[2].dishes.push(dishOf(dRice, '主食'));
    meals[3].dishes.push(milk, fruit);

    var all = [];
    meals.forEach(function (m) { all = all.concat(m.dishes); });
    var totals = NUTRITION.sum(all);
    var targets = Object.assign({}, GUIDE.targets, GUIDE.profiles[prefs.profile] || {}, { sodium: GUIDE.targets.sodium });
    var sc = NUTRITION.score(totals, targets);

    // 采购清单:按家庭人数放大
    var fam = Math.max(1, prefs.family || 1);
    var groceryOrder = ['蔬菜', '肉禽蛋', '水产海鲜', '水果', '粮油豆奶', '干货干货'];
    var groceryMap = {};
    function grpOf(g) {
      if (g === '菜' || g === '果') return g === '果' ? '水果' : '蔬菜';
      if (g === '肉' || g === '蛋') return '肉禽蛋';
      if (g === '水产') return '水产海鲜';
      if (g === '粮' || g === '豆' || g === '奶') return '粮油豆奶';
      if (g === '干') return '干货干货';
      return '干货干货';
    }
    var conds = {};
    all.forEach(function (d) {
      (d.ingredients || []).forEach(function (ig) {
        if (!ig.gr) return;
        if (ig.gr === '调味' || ig.gr === '油' || ig.gr === '水') { (conds[ig.n] = conds[ig.n] || 0) + 0; return; }
        var key = ig.n.replace(/\s+/g, '');
        var g = grpOf(ig.gr);
        if (!groceryMap[g]) groceryMap[g] = {};
        groceryMap[g][key] = (groceryMap[g][key] || 0) + Math.round(ig.g * fam);
      });
    });
    var grocery = [];
    groceryOrder.forEach(function (g) {
      if (!groceryMap[g]) return;
      grocery.push({ group: g, items: Object.keys(groceryMap[g]).map(function (name) { return { name: name, grams: groceryMap[g][name] }; }) });
    });

    var usedIds = [];
    all.forEach(function (d) { if (!d.item) usedIds.push(d.id); });

    var notes = [];
    all.forEach(function (d) { if (d.occa) notes.push(d.name + ' 属"偶尔吃"，不宜高频'); });
    if (notes.length) notes.push('本周尽量别重复出现以上菜品');

    return {
      date: dateStr(new Date()),
      dateLabel: '星期' + weekDay(new Date()),
      seed: seed,
      profileLabel: (GUIDE.profiles[prefs.profile] || GUIDE.profiles.normal).label,
      family: fam,
      meals: meals,
      totals: totals,
      targets: targets,
      score: sc,
      grade: NUTRITION.grade(sc),
      tips: NUTRITION.tips(totals, targets),
      varieties: totals.varieties,
      grocery: grocery,
      conds: Object.keys(conds),
      notes: notes,
      usedIds: usedIds
    };
  }

  function recommend(prefs, dateKey) {
    prefs = prefs || {};
    var base = dateKey || dateStr(new Date());
    var seed = hashStr(base + '_' + (prefs.seedCount || 0));
    return build(seed, prefs);
  }

  return {
    recommend: recommend,
    build: build,
    hashStr: hashStr,
    dateStr: dateStr
  };
});