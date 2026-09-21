(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) module.exports = factory();
  else root.NUTRITION = factory();
})(this, function () {
  function safeN(r) {
    if (!r) return { kcal: 0, protein: 0, fat: 0, carb: 0, fiber: 0, sodium: 0, vegGram: 0 };
    return {
      kcal: r.kcal || 0,
      protein: r.protein || 0,
      fat: r.fat || 0,
      carb: r.carb || 0,
      fiber: r.fiber || 0,
      sodium: r.sodium || 0,
      vegGram: r.vegGram || 0
    };
  }

  // 多道菜合并营养
  function sum(dishes) {
    var t = { kcal: 0, protein: 0, fat: 0, carb: 0, fiber: 0, sodium: 0, vegGram: 0, varieties: 0 };
    if (!dishes || !dishes.length) return t;
    var inSet = {};
    dishes.forEach(function (d) {
      var n = safeN(d.nutrition);
      t.kcal += n.kcal;
      t.protein += n.protein;
      t.fat += n.fat;
      t.carb += n.carb;
      t.fiber += n.fiber;
      t.sodium += n.sodium;
      t.vegGram += n.vegGram;
      (d.ingredients || []).forEach(function (ig) {
        var key = String(ig.n || ig.name || '').replace(/\s+/g, '');
        if (key) inSet[key] = 1;
      });
    });
    t.varieties = Object.keys(inSet).length;
    return t;
  }

  function pct(cur, target) {
    return Math.round((cur / (target || 1)) * 100);
  }

  // 达成水平: low 偏低 / ok 合理 / high 偏高 / very 超标
  function level(cur, target, isNa) {
    var p = pct(cur, target);
    if (isNa) {
      if (p > 150) return 'very';
      if (p > 100) return 'high';
      if (p >= 70) return 'ok';
      return 'low';
    }
    if (p < 70) return 'low';
    if (p <= 115) return 'ok';
    if (p <= 150) return 'high';
    return 'very';
  }

  function labelOf(lvl, n) {
    var map = { low: '偏低', ok: '合理', high: '偏高', very: '超标' };
    return map[lvl] || '合理';
  }

  // 根据总量与目标算一日评分（0~100）
  function score(totals, targets) {
    var s = 100;
    var energyP = pct(totals.kcal || 0, targets.energy);
    if (energyP < 70 || energyP > 130) s -= 25;
    else if (energyP < 85 || energyP > 120) s -= 10;
    var naP = pct(totals.sodium || 0, targets.sodium);
    if (naP > 150) s -= 25;
    else if (naP > 110) s -= 15;
    else if (naP > 100) s -= 8;
    var vegP = pct(totals.vegGram || 0, targets.veg);
    if (vegP < 60) s -= 15;
    else if (vegP < 90) s -= 6;
    if ((totals.varieties || 0) < 12) s -= 10;
    var proP = pct(totals.protein || 0, targets.protein);
    if (proP < 70 || proP > 150) s -= 10;
    var fatP = totals.kcal ? (totals.fat * 9 / totals.kcal) * 100 : 40;
    if (fatP > 30) s -= 12;
    return Math.max(0, Math.min(100, s));
  }

  function grade(s) {
    if (s >= 90) return '优秀';
    if (s >= 75) return '良好';
    if (s >= 60) return '及格';
    return '加油';
  }

  // 根据差值生成建议
  function tips(totals, targets) {
    var out = [];
    if ((totals.sodium || 0) > targets.sodium) {
      out.push('今日钠偏高，建议少放盐、豉油，老火汤调味减半');
    }
    if ((totals.vegGram || 0) < targets.veg) {
      out.push('蔬菜还没吃够，晚餐再加一份白灼菜心或西兰花');
    }
    var fatP = totals.kcal ? (totals.fat * 9 / totals.kcal) * 100 : 0;
    if (fatP > 30) out.push('脂肪供能偏高，控制油炸菜与肥肉，白切鸡建议去皮');
    if ((totals.varieties || 0) < 12) out.push('食材只有 ' + totals.varieties + ' 种，加一份杂粮或豆制品凑齐 12 种');
    if (out.length === 0) out.push('今日搭配较合理，继续保持清淡饮食');
    return out;
  }

  return {
    sum: sum,
    pct: pct,
    level: level,
    score: score,
    grade: grade,
    tips: tips,
    labelOf: labelOf
  };
});