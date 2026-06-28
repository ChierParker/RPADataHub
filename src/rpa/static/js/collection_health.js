/**
 * 店铺采集健康度 — 数据加载与渲染
 * 从 collection_health.html 提取
 */
(function () {
  'use strict';

  // 活跃店铺列表（由模板注入）
  var ACTIVE_SHOPS = window.__HEALTH_SHOPS__ || [];

  fetch('/rpa/api/collection/health')
    .then(function (r) { return r.json(); })
    .then(function (d) {
      var days = [];
      for (var i = 6; i >= 0; i--) {
        var dt = new Date(Date.now() - i * 864e5);
        days.push(dt.toISOString().split('T')[0]);
      }

      var map = {};
      (d.records || []).forEach(function (r) {
        var k = r.shop_name + '_' + r.dt;
        if (!map[k]) map[k] = {};
        map[k][r.collect_result] = (map[k][r.collect_result] || 0) + r.cnt;
      });

      // 活跃店铺 + 有采集记录的店铺合并
      var shopNames = (d.records || []).map(function (r) { return r.shop_name; });
      var shops = Array.from(new Set(ACTIVE_SHOPS.concat(shopNames)));

      var h = '';
      shops.forEach(function (shop) {
        h += '<tr><td>' + shop + '</td>';
        var failStreak = 0;

        days.forEach(function (dt) {
          var k = shop + '_' + dt;
          var rec = map[k] || {};
          var s = rec['SUCCESS'] || 0;
          var f = rec['FAILED'] || 0;
          var n = rec['NO_DATA'] || 0;

          var color = s > 0 ? '#22c55e' : f > 0 ? '#ef4444' : n > 0 ? '#9ca3af' : '#e5e7eb';
          var tip = s > 0 ? '成功 ' + s : f > 0 ? '失败' : '无数据';

          if (f > 0) failStreak++;
          else failStreak = 0;

          h += '<td class="text-center"><span style="display:inline-block;width:24px;height:24px;'
            + 'border-radius:50%;background:' + color + '" title="' + dt + ': ' + tip + '"></span></td>';
        });

        var badge = failStreak >= 3
          ? '<span class="badge bg-danger">异常</span>'
          : failStreak > 0
            ? '<span class="badge bg-warning">注意</span>'
            : '<span class="badge bg-success">正常</span>';
        h += '<td>' + badge + '</td></tr>';
      });

      document.getElementById('body').innerHTML = h
        || '<tr><td colspan="9" class="text-center text-muted">暂无数据</td></tr>';
    })
    .catch(function () {
      document.getElementById('body').innerHTML =
        '<tr><td colspan="9" class="text-center text-danger">加载失败，请重试</td></tr>';
    });
})();
