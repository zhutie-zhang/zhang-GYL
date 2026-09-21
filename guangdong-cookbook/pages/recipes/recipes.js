const RECIPES = require('../../utils/recipes.js');

Page({
  data: {
    kind: '全部',
    kinds: [],
    keyword: '',
    list: []
  },

  onLoad: function () {
    var kinds = ['全部'].concat(RECIPES.list.map(function (r) { return r.kind; }).filter(function (k, i, a) { return a.indexOf(k) === i; }));
    this.setData({ kinds: kinds });
    this.apply();
  },

  onInput: function (e) {
    this.setData({ keyword: e.detail.value || '' });
    this.apply();
  },

  onKind: function (e) {
    this.setData({ kind: e.currentTarget.dataset.k, keyword: '' });
    this.apply();
  },

  apply: function () {
    var kw = (this.data.keyword || '').trim().toLowerCase();
    var kind = this.data.kind;
    var list = RECIPES.list.filter(function (r) {
      if (kind !== '全部' && r.kind !== kind) return false;
      if (!kw) return true;
      var hay = (r.name + ' ' + r.style + ' ' + (r.tags || []).join(' ') + ' ' + (r.ingredients || []).map(function (ig) { return ig.n; }).join(' ')).toLowerCase();
      return hay.indexOf(kw) >= 0;
    });
    this.setData({ list: list });
  },

  goDetail: function (e) {
    wx.navigateTo({ url: '/pages/detail/detail?id=' + e.currentTarget.dataset.id });
  }
});