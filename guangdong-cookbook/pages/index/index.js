const STORE = require('../../utils/store.js');
const RECOMMEND = require('../../utils/recommend.js');
const GUIDE = require('../../utils/guide.js');
const NUTRITION = require('../../utils/nutrition.js');

Page({
  data: {
    menu: null,
    seedCount: 0,
    profileKey: 'normal',
    profiles: GUIDE.profiles,
    bars: [],
    showGrocery: false,
    showAnalysis: true
  },

  onLoad: function () {
    this.refresh();
  },

  onShow: function () {
    if (this.data.menu) return;
    this.refresh();
  },

  refresh: function () {
    var prefs = STORE.prefs();
    var seedCount = parseInt(STORE.get('seedCount', '0') || '0', 10);
    prefs.seedCount = seedCount;
    var menu = RECOMMEND.recommend(prefs);
    menu.meals.forEach(function (m) {
      m.kcal = m.dishes.reduce(function (s, d) { return s + d.kcal; }, 0);
    });
    getApp().globalData.menu = menu;
    this.setData({
      menu: menu,
      seedCount: seedCount,
      profileKey: prefs.profile,
      bars: this.buildBars(menu),
      showGrocery: false
    });
  },

  buildBars: function (menu) {
    var t = menu.totals, tg = menu.targets;
    var items = [
      { key: '能量', unit: '千卡', cur: t.kcal, target: tg.energy },
      { key: '蛋白质', unit: '克', cur: t.protein, target: tg.protein },
      { key: '脂肪', unit: '克', cur: t.fat, target: tg.fat },
      { key: '碳水', unit: '克', cur: t.carb, target: tg.carb },
      { key: '钠', unit: '毫克', cur: t.sodium, target: tg.sodium, na: true },
      { key: '蔬菜', unit: '克', cur: t.vegGram, target: tg.veg }
    ];
    return items.map(function (it) {
      var p = NUTRITION.pct(it.cur, it.target);
      var lv = NUTRITION.level(it.cur, it.target, it.na);
      return {
        key: it.key, unit: it.unit,
        cur: Math.round(it.cur), target: it.target,
        pct: Math.min(200, p), width: Math.min(100, p),
        lv: lv, label: NUTRITION.labelOf(lv, it.na)
      };
    });
  },

  changeMenu: function () {
    var seedCount = this.data.seedCount + 1;
    STORE.set('seedCount', String(seedCount));
    this.refresh();
  },

  onProfileChange: function (e) {
    var prefs = STORE.prefs();
    prefs.profile = e.currentTarget.dataset.key;
    STORE.savePrefs(prefs);
    this.refresh();
  },

  toggleGrocery: function () {
    this.setData({ showGrocery: !this.data.showGrocery });
  },

  toggleAnalysis: function () {
    this.setData({ showAnalysis: !this.data.showAnalysis });
  },

  goDetail: function (e) {
    var id = e.currentTarget.dataset.id;
    if (!id || id === 'milk' || id === 'fruit') return;
    wx.navigateTo({ url: '/pages/detail/detail?id=' + id });
  },

  goRecord: function () {
    wx.navigateTo({ url: '/pages/record/record' });
  }
});