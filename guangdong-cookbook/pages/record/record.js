const RECIPES = require('../../utils/recipes.js');
const NUTRITION = require('../../utils/nutrition.js');
const STORE = require('../../utils/store.js');
const GUIDE = require('../../utils/guide.js');

function today() {
  var d = new Date();
  return d.getFullYear() + '-' + (d.getMonth() + 1 < 10 ? '0' : '') + (d.getMonth() + 1) + '-' + (d.getDate() < 10 ? '0' : '') + d.getDate();
}

Page({
  data: {
    date: '',
    kinds: [],
    groups: [],
    selected: {},
    selCount: 0,
    summary: null,
    bars: []
  },

  onLoad: function () {
    var groups = [];
    RECIPES.list.slice().sort(function (a, b) { return (a.kind + a.name) < (b.kind + b.name) ? -1 : 1; }).forEach(function (r) {
      var g = groups[groups.length - 1];
      if (!g || g.kind !== r.kind) { g = { kind: r.kind, items: [] }; groups.push(g); }
      g.items.push(r);
    });
    this.setData({
      date: today(),
      kinds: groups.map(function (g) { return g.kind; }),
      groups: groups
    });
  },

  onDate: function (e) {
    this.setData({ date: e.detail.value });
  },

  toggle: function (e) {
    var id = e.currentTarget.dataset.id;
    var sel = this.data.selected;
    sel[id] = !sel[id];
    this.setData({ selected: sel });
    this.recalc();
  },

  fillMenu: function () {
    var menu = getApp().globalData.menu;
    if (!menu) { wx.showToast({ title: '先去首页生成今日推荐', icon: 'none' }); return; }
    var sel = {};
    menu.meals.forEach(function (m) {
      m.dishes.forEach(function (d) { if (d.id && d.id !== 'milk' && d.id !== 'fruit') sel[d.id] = true; });
    });
    this.setData({ selected: sel });
    this.recalc();
  },

  clearAll: function () {
    this.setData({ selected: {} });
    this.recalc();
  },

  recalc: function () {
    var selected = this.data.selected;
    var list = [];
    Object.keys(selected).forEach(function (id) {
      if (selected[id] && RECIPES.byId[id]) list.push(RECIPES.byId[id]);
    });
    if (!list.length) {
      this.setData({ selCount: 0, summary: null, bars: [] });
      return;
    }
    var totals = NUTRITION.sum(list);
    var targets = Object.assign({}, GUIDE.targets, GUIDE.profiles.normal);
    var sc = NUTRITION.score(totals, targets);
    this.setData({
      selCount: list.length,
      summary: { kcal: Math.round(totals.kcal), score: sc, grade: NUTRITION.grade(sc), varieties: totals.varieties, tips: NUTRITION.tips(totals, targets) },
      bars: this.bars(totals, targets)
    });
  },

  bars: function (t, tg) {
    var arr = [
      { k: '能量', v: t.kcal, t: tg.energy, u: '千卡' },
      { k: '蛋白质', v: t.protein, t: tg.protein, u: '克' },
      { k: '脂肪', v: t.fat, t: tg.fat, u: '克' },
      { k: '钠', v: t.sodium, t: tg.sodium, u: '毫克', na: true },
      { k: '蔬菜', v: t.vegGram, t: tg.veg, u: '克' }
    ];
    return arr.map(function (b) {
      var p = NUTRITION.pct(b.v, b.t);
      return { k: b.k, v: Math.round(b.v), u: b.u, pct: Math.min(100, p), lv: NUTRITION.level(b.v, b.t, b.na), label: NUTRITION.labelOf(NUTRITION.level(b.v, b.t, b.na), b.na) };
    });
  },

  save: function () {
    var self = this;
    if (!this.data.summary) { wx.showToast({ title: '先勾选今天吃了什么', icon: 'none' }); return; }
    var selected = this.data.selected;
    var ids = [];
    var names = [];
    Object.keys(selected).forEach(function (id) {
      if (selected[id] && RECIPES.byId[id]) { ids.push(id); names.push(RECIPES.byId[id].name); }
    });
    var rec = {
      date: this.data.date,
      ids: ids,
      names: names.join('、'),
      totals: this.data.summary,
      count: ids.length
    };
    STORE.saveRecord(rec);
    wx.showToast({ title: '已记录，评分 ' + this.data.summary.score, icon: 'none' });
    setTimeout(function () { wx.navigateBack(); }, 900);
  }
});