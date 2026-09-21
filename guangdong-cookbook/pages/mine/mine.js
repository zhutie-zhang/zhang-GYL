const STORE = require('../../utils/store.js');
const GUIDE = require('../../utils/guide.js');

Page({
  data: {
    profiles: GUIDE.profiles,
    profileKey: 'normal',
    family: 3,
    taste: 'light',
    vetoList: [
      { k: 'beef', label: '不吃牛肉', on: false },
      { k: 'seafood', label: '海鲜过敏', on: false },
      { k: 'organ', label: '不吃内脏', on: false },
      { k: 'preserved', label: '不吃腊味', on: false },
      { k: 'veg', label: '素食（蛋奶素）', on: false }
    ],
    records: []
  },

  onShow: function () {
    this.load();
  },

  load: function () {
    var p = STORE.prefs();
    var veto = p.veto || [];
    this.setData({
      profileKey: p.profile,
      family: p.family,
      taste: p.taste,
      vetoList: this.data.vetoList.map(function (v) {
        v.on = veto.indexOf(v.k) >= 0;
        return v;
      }),
      records: STORE.listRecords()
    });
  },

  save: function (patch) {
    var p = STORE.prefs();
    Object.assign(p, patch);
    STORE.savePrefs(p);
    this.setData(patch);
  },

  onProfile: function (e) {
    var k = e.currentTarget.dataset.k;
    this.save({ profile: k });
    wx.showToast({ title: '已按「' + (GUIDE.profiles[k] || {}).label + '」搭配', icon: 'none' });
  },

  familySub: function () { if (this.data.family > 1) this.save({ family: this.data.family - 1 }); },
  familyAdd: function () { if (this.data.family < 10) this.save({ family: this.data.family + 1 }); },

  onTaste: function (e) {
    this.save({ taste: e.currentTarget.dataset.k });
  },

  onVeto: function (e) {
    var k = e.currentTarget.dataset.k;
    var list = this.data.vetoList.map(function (v) {
      if (v.k === k) v.on = !v.on;
      return v;
    });
    this.setData({ vetoList: list });
    this.save({ veto: list.filter(function (v) { return v.on; }).map(function (v) { return v.k; }) });
  },

  goRecord: function () {
    wx.navigateTo({ url: '/pages/record/record' });
  },

  delRecord: function (e) {
    var date = e.currentTarget.dataset.date;
    wx.showModal({
      title: '删除记录',
      content: '确定删除 ' + date + ' 的记录吗？',
      success: (res) => {
        if (res.confirm) {
          this.setData({ records: STORE.removeRecord(date) });
        }
      }
    });
  }
});