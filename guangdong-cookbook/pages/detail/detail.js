const RECIPES = require('../../utils/recipes.js');
const GUIDE = require('../../utils/guide.js');
const NUTRITION = require('../../utils/nutrition.js');

Page({
  data: {
    r: null,
    nutRows: [],
    notFound: false
  },

  onLoad: function (options) {
    var r = RECIPES.byId[options.id];
    if (!r) {
      this.setData({ notFound: true });
      return;
    }
    var t = GUIDE.targets;
    var maps = [
      { k: '能量', v: r.nutrition.kcal, unit: '千卡', target: t.energy },
      { k: '蛋白质', v: r.nutrition.protein, unit: '克', target: t.protein },
      { k: '脂肪', v: r.nutrition.fat, unit: '克', target: t.fat },
      { k: '碳水化合物', v: r.nutrition.carb, unit: '克', target: t.carb },
      { k: '膳食纤维', v: r.nutrition.fiber, unit: '克', target: t.fiber },
      { k: '钠', v: r.nutrition.sodium, unit: '毫克', target: t.sodium }
    ];
    var rows = maps.map(function (m) {
      var p = NUTRITION.pct(m.v, m.target);
      return { k: m.k, v: m.v, unit: m.unit, pct: p };
    });
    this.setData({ r: r, nutRows: rows });
    wx.setNavigationBarTitle({ title: r.name });
  }
});