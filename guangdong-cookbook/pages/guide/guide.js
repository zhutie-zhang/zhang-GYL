const GUIDE = require('../../utils/guide.js');

Page({
  data: {
    pagoda: [],
    principles: [],
    myths: [],
    habits: [],
    prOpen: -1,
    mythOpen: 0
  },

  onLoad: function () {
    var pagoda = GUIDE.pagoda.map(function (p, i) {
      return Object.assign({}, p, { width: [94, 88, 78, 66, 52][i] });
    });
    this.setData({
      pagoda: pagoda,
      principles: GUIDE.principles,
      myths: GUIDE.myths,
      habits: GUIDE.habitCards,
      prOpen: 0
    });
  },

  togglePr: function (e) {
    var i = e.currentTarget.dataset.i;
    this.setData({ prOpen: this.data.prOpen === i ? -1 : i });
  },

  toggleMyth: function (e) {
    var i = e.currentTarget.dataset.i;
    this.setData({ mythOpen: this.data.mythOpen === i ? -1 : i });
  }
});