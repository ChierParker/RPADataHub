/**
 * 店铺管理 — 数据加载、排序、编辑、导出
 * 从 shops.html 提取
 */
(function () {
  'use strict';
  var currentPage = 1, shopSortCol = '', shopSortDir = 'desc';

  window.sortShopBy = function (col) {
    if (shopSortCol === col) shopSortDir = shopSortDir === 'asc' ? 'desc' : 'asc';
    else { shopSortCol = col; shopSortDir = 'desc'; }
    document.querySelectorAll('.sort-indicator').forEach(function (el) { el.textContent = ''; });
    var ind = document.getElementById('ssort_' + col);
    if (ind) ind.textContent = shopSortDir === 'asc' ? ' ▲' : ' ▼';
    loadShops(1);
  };

  window.loadShops = function (page) {
    currentPage = page || currentPage;
    var perPage = document.getElementById('shopPageSize').value || 15;
    var qs = 'page=' + currentPage + '&per_page=' + perPage + '&sort=' + shopSortCol + '&order=' + shopSortDir;
    var s = document.getElementById('fSearch').value, p = document.getElementById('fPlatform').value,
      st = document.getElementById('fStatus').value;
    if (s) qs += '&search=' + encodeURIComponent(s);
    if (p) qs += '&platform=' + encodeURIComponent(p);
    if (st) qs += '&status=' + st;
    fetch('/rpa/api/shops/data?' + qs)
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) {
        var platHtml = '<option value="">全部平台</option>';
        (d.platforms || []).forEach(function (p) { platHtml += '<option value="' + p + '">' + p + '</option>'; });
        document.getElementById('fPlatform').innerHTML = platHtml;
        if (p) document.getElementById('fPlatform').value = p;
        var html = '';
        if (!d.records || !d.records.length) {
          html = '<tr><td colspan="8" class="text-center text-muted py-4">无匹配数据</td></tr>';
        } else {
          d.records.forEach(function (r) {
            var statusBadge = r.status == 1 ? '<span class="badge bg-success">活跃</span>'
              : r.status == 0 ? '<span class="badge bg-warning">低频</span>' : '<span class="badge bg-secondary">停用</span>';
            html += '<tr><td><code>' + r.shop_id + '</code></td><td>' + r.shop_name + '</td><td>' + r.platform + '</td>'
              + '<td>' + r.bu + '</td><td>' + r.email + '</td><td>' + statusBadge + '</td><td>' + (r.create_time || '-') + '</td>'
              + '<td><button class="btn btn-outline-secondary btn-sm" onclick="showEdit(\'' + r.shop_id + '\')"><i class="bi bi-pencil"></i></button></td></tr>';
          });
        }
        document.getElementById('shopBody').innerHTML = html;
        var total = d.total || 0, pages = Math.max(1, Math.ceil(total / perPage));
        document.getElementById('shopInfo').textContent = '共 ' + total + ' 条';
        var btns = '';
        for (var i = Math.max(1, currentPage - 2); i <= Math.min(pages, currentPage + 2); i++)
          btns += '<button class="btn btn-sm ' + (i === currentPage ? 'btn-dark' : 'btn-outline-secondary') + '" onclick="loadShops(' + i + ')">' + i + '</button>';
        document.getElementById('shopBtns').innerHTML = btns;
        document.getElementById('shopPager').style.display = 'flex';
      }).catch(function (err) {
        document.getElementById('shopBody').innerHTML = '<tr><td colspan="8" class="text-center text-danger py-4">加载失败: ' + err.message + '</td></tr>';
      });
  };


  window.showEdit = function (shopId) {
    document.getElementById('shopModalTitle').textContent = shopId ? '编辑店铺: ' + shopId : '新增店铺';
    if (shopId) {
      fetch('/rpa/api/shops/data?search=' + encodeURIComponent(shopId))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var r = (d.records || []).find(function (x) { return x.shop_id === shopId; });
          if (r) {
            document.getElementById('eShopId').value = r.shop_id;
            document.getElementById('eShopId').readOnly = true;
            document.getElementById('eShopName').value = r.shop_name;
            document.getElementById('ePlatform').value = r.platform || '';
            document.getElementById('eBu').value = r.bu || '';
            document.getElementById('eEmail').value = r.email || '';
            document.getElementById('eStatus').value = r.status;
          }
        });
    } else {
      document.getElementById('eShopId').value = '';
      document.getElementById('eShopId').readOnly = false;
      document.getElementById('eShopName').value = '';
      document.getElementById('ePlatform').value = '';
      document.getElementById('eBu').value = '';
      document.getElementById('eEmail').value = '';
      document.getElementById('eStatus').value = '1';
    }
    new bootstrap.Modal(document.getElementById('shopModal')).show();
  };

  window.saveShop = function () {
    var data = {
      shop_id: document.getElementById('eShopId').value,
      shop_name: document.getElementById('eShopName').value,
      platform: document.getElementById('ePlatform').value,
      bu: document.getElementById('eBu').value,
      email: document.getElementById('eEmail').value,
      status: parseInt(document.getElementById('eStatus').value),
    };
    if (!data.shop_id || !data.shop_name) return showToast('店铺ID和名称不能为空', 'error');
    fetch('/rpa/api/shops/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.success) { showToast('保存成功'); document.getElementById('shopModal').querySelector('.btn-close').click(); loadShops(1); }
        else showToast(d.error, 'error');
      });
  };

  window.exportShops = function () {
    var s = document.getElementById('fSearch').value, p = document.getElementById('fPlatform').value,
      st = document.getElementById('fStatus').value;
    var qs = '';
    if (s) qs += '&search=' + encodeURIComponent(s);
    if (p) qs += '&platform=' + p;
    if (st) qs += '&status=' + st;
    window.open('/rpa/api/shops/export?' + qs, '_blank');
  };

  loadShops(1);
})();

