const SimpleMetaService = require('../services/simpleMetaService');
const cafe24Service = require('../services/cafe24Service');
const tiktokService = require('../services/tiktokService');
const { getDistribution, buildDistributionBlocks } = require('../services/orderDistributionService');
const { getNow, getYesterdayKST, makeMessenger } = require('../utils');
const { saveSnapshot, loadSnapshot, clearSnapshot } = require('../services/proteinSnapshotService');

const metaService = new SimpleMetaService();

const TOKEN_URL = 'https://lalasweet17.cafe24api.com/api/v2/oauth/authorize?response_type=code&client_id=125DtymxJVUnP0KbGnXRtC&state=slack&redirect_uri=https%3A%2F%2Fcafe24-ad-bot-production.up.railway.app%2Foauth%2Fcallback&scope=mall.read_order%2Cmall.read_product';
const TOKEN_ERROR_MSG = `❌ 카페24 토큰이 만료되었습니다.\n──────────────────────\n아래 링크로 접속하여 카페24 로그인 후 토큰 발급을 해주세요.\n<${TOKEN_URL}|👉 카페24 토큰 발급 링크>`;

// 제과 전체 상품코드 (팝콘+990딜+웨하스+퍼프+아몬드스윗제과+꼬숩두유+블트깡) — 단백질쉐이크(226, 235, 238)만 제외
// 239, 255: 신규 팝콘 상품 (2026-07 옵션 개편) / 236: 블트깡 (2026-07-15부터 제과 총 현황에 포함)
const JEGWA_ALL_PRODUCT_NOS = [135, 161, 239, 255, 193, 156, 175, 178, 140, 167, 236];

// 팝콘 상품번호 (구 135+161, 신 239+255)
const POPCORN_PRODUCT_NOS = [135, 161, 239, 255];

const PROFIT_RATES = {
  팝콘: 0.45,
  아몬드스윗: -0.374,
  블트깡: 0.485, // 블트깡 주문 0건일 때 폴백 (평시에는 BLT_SET_RATES 가중평균 사용)
};

// ── 블랙트러플 하몽깡(236) 구성별 수익률 (묶음 선택 개입 수 기준) ──
// 실제 판매비중으로 가중평균 자동 계산. 구성 추가/수익률 변경 시 여기만 수정
const BLT_SET_RATES = {
  10: 0.522,
  15: 0.481,
  20: 0.495,
  30: 0.461,
};

// ── 단백질쉐이크 226 세트별 수익률 (신 포맷 기준: 1/2/3/4/6/8세트) ──
const COUPON_RATIO = 0.45;
const PROTEIN_SET_BASE_RATES = {
  coupon:   { 1: 0.498, 2: 0.404, 3: 0.436, 4: 0.318, 6: 0.280, 8: 0.214 },
  noCoupon: { 1: 0.498, 2: 0.444, 3: 0.462, 4: 0.346, 6: 0.302, 8: 0.234 },
};
const PROTEIN_SET_RATES = Object.fromEntries(
  Object.keys(PROTEIN_SET_BASE_RATES.coupon).map(set => [
    parseInt(set),
    COUPON_RATIO * PROTEIN_SET_BASE_RATES.coupon[set] + (1 - COUPON_RATIO) * PROTEIN_SET_BASE_RATES.noCoupon[set],
  ])
);

// 990딜(235)은 판매 종료로 손익 표시에서 완전 제거 (2026-07-15). 세트별 수익률 상수 필요 시 git 히스토리 참조
const PROTEIN_CONFIG = {
  미끼수익률: 0.49,
  품절이후수익률: 0.3482,
  단일수익률구간: [
    { from: '2026-06-27', rate: 0.4534, label: '45.34%' },
    { from: '2026-07-01', rate: 0.40,   label: '40%'    },
    { from: '2026-07-02', rate: 0.2762, label: '27.62%' },
    { from: '2026-07-06', rate: 0.3482, label: '34.82%' },
  ],
};

// ─────────────────────────────────────────
// 제품별 추가 비용 (알림톡 등) — 평소에는 0
// ─────────────────────────────────────────
const EXTRA_COST = {
  팝콘: { amount: 850000, date: '2026-07-01' },
};

// ─────────────────────────────────────────
// 세트별 가중평균 수익률 계산 헬퍼
// ─────────────────────────────────────────
function calcWeightedRate(setCounts, fallback, rates = PROTEIN_SET_RATES) {
  const totalCount = Object.values(setCounts || {}).reduce((a, b) => a + b, 0);
  if (totalCount === 0) return { rate: fallback, label: `${(fallback * 100).toFixed(2)}%`, totalCount: 0 };
  const rate = Object.entries(setCounts).reduce((sum, [set, count]) => {
    return sum + (rates[parseInt(set)] || 0) * count;
  }, 0) / totalCount;
  return { rate, label: `${(rate * 100).toFixed(2)}%`, totalCount };
}

const DASHBOARD_URL = 'https://lalasweet-ad-dashboard-l79nkrhnocw6pranabzy8v.streamlit.app/mobile';

function cpaGapLabel(target, actual) {
  if (!target || !actual) return '';
  const diff = (actual - target) / target * 100;
  const emoji = diff > 0 ? '🔴' : '🟢';
  const sign = diff > 0 ? '+' : '';
  return ` ${emoji} ${sign}${diff.toFixed(1)}%`;
}

// view: 'summary'(기존 /손익확인_제과) | '팝콘' | '단쉐' | '블트하' (상품별 명령어 — 본문에 해당 상품 상세, 나머지는 스레드)
async function handleJegwaCheck(client, channel, threadTs, targetDate, view = 'summary') {
  const { time } = getNow();
  const threadBase = threadTs ? { thread_ts: threadTs } : {};
  const loading = await client.chat.postMessage({ channel, ...threadBase, text: `⏳ 제과 손익 현황 조회 중... (${targetDate} ${time})` });
  try {
    // meta235(단쉐_990): 990딜 판매 종료 후에도 잔여 집행 대비 제과 총 현황 광고비 차감용으로만 유지
    const [metaJegwa, metaA, meta226, tiktok226, meta235, meta236, tiktok236, salesAll, salesA, split226, split236] = await Promise.all([
      metaService.getMetaStats('제과', targetDate),
      metaService.getMetaStats('팝콘', targetDate, '990'),
      metaService.getMetaStats('단백질쉐이크', targetDate, '990'),
      tiktokService.getAdStats('단백질쉐이크', targetDate, targetDate),
      metaService.getMetaStats('단쉐_990', targetDate),
      metaService.getMetaStats('블트깡출시', targetDate),
      tiktokService.getAdStats('블트깡출시', targetDate, targetDate),
      cafe24Service.getSalesByProduct(JEGWA_ALL_PRODUCT_NOS, { startDate: targetDate, endDate: targetDate }),
      cafe24Service.getSalesByProduct(POPCORN_PRODUCT_NOS, { startDate: targetDate, endDate: targetDate }),
      cafe24Service.getProduct226Split({ startDate: targetDate, endDate: targetDate }),
      cafe24Service.getProduct236Split({ startDate: targetDate, endDate: targetDate }),
    ]);

    const products = salesAll.products;
    const getRev = (...nos) => nos.reduce((s, no) => s + (products.find(p => p.productNo == no)?.revenue || 0), 0);
    const fmt = n => Math.round(n).toLocaleString('ko-KR');

    // ── 제과 총 현황 (단쉐 226/235/238만 제외, 블트깡 포함) ──
    const getExtraCost = (item) => {
      if (!item.amount) return 0;
      return (item.date === null || item.date === targetDate) ? item.amount : 0;
    };
    const totalRevenue = products.reduce((s, p) => s + p.revenue, 0);
    const totalOrders = salesAll.totalOrders;
    const FIXED_AD_SPEND = 500000;
    const extraCostA = getExtraCost(EXTRA_COST.팝콘);
    // 블트깡 캠페인('제과_블트깡출시')은 '제과' 집계에 포함되므로 차감하지 않음 (2026-07-15 블트깡 포함 개편)
    const totalAdSpend = metaJegwa.totalSpend - meta226.totalSpend - meta235.totalSpend + FIXED_AD_SPEND + extraCostA;
    const profit = Math.round(totalRevenue / 1.1 * 0.45) - totalAdSpend;
    const avgOrderValue = totalOrders > 0 ? Math.round(totalRevenue / totalOrders) : 0;

    // ── 팝콘 (135+161+239+255) ──
    const revA = getRev(...POPCORN_PRODUCT_NOS);
    const totalAdSpendA = metaA.totalSpend + extraCostA;
    const profitA = Math.round(revA / 1.1 * PROFIT_RATES.팝콘) - totalAdSpendA;
    const avgOrderValueA = salesA.totalOrders > 0 ? Math.round(revA / salesA.totalOrders) : 0;
    const matchRateA = metaA.totalPurchases > 0 ? (salesA.totalOrders / metaA.totalPurchases * 100).toFixed(1) : '0.0';
    const targetCpaA = metaA.totalPurchases > 0 ? Math.round((revA / 1.1 * PROFIT_RATES.팝콘 - extraCostA) / metaA.totalPurchases) : 0;

    // ── 블랙트러플 하몽깡 (236) ──
    const rev236 = split236.revenue;
    const orders236 = split236.totalOrders;
    // 구성별(10/15/20/30개입) 판매비중 가중평균 수익률 — 주문 0건이면 PROFIT_RATES.블트깡 폴백
    const { rate: rate236, label: rateLabel236 } = calcWeightedRate(
      split236.setCounts,
      PROFIT_RATES.블트깡,
      BLT_SET_RATES
    );
    const adSpend236 = meta236.totalSpend + tiktok236.totalSpend;
    const purchases236Meta = meta236.totalPurchases;
    const purchases236Tiktok = tiktok236.totalPurchases;
    const purchases236 = purchases236Meta + purchases236Tiktok;
    const profit236 = Math.round(rev236 / 1.1 * rate236) - adSpend236;
    const avgOrderValue236 = orders236 > 0 ? Math.round(rev236 / orders236) : 0;
    const matchRate236 = purchases236 > 0 ? (orders236 / purchases236 * 100).toFixed(1) : '0.0';
    const targetCpa236 = purchases236 > 0 ? Math.round((rev236 / 1.1 * rate236) / purchases236) : 0;
    const cpa236Meta = purchases236Meta > 0 ? Math.round(meta236.totalSpend / purchases236Meta) : 0;
    const cpa236Tiktok = purchases236Tiktok > 0 ? Math.round(tiktok236.totalSpend / purchases236Tiktok) : 0;

    const bltkkang236Blocks = [
      { type: 'section', text: { type: 'mrkdwn', text: `*▸ 블랙트러플 하몽깡 (236)*` } },
      {
        type: 'section',
        text: { type: 'mrkdwn', text: `🏷️ 매출 *${fmt(rev236)}원* | 손익 *${fmt(profit236)}원* | 광고비 *${fmt(adSpend236)}원* | 구매 *${fmt(orders236)}건* | 객단가 *${fmt(avgOrderValue236)}원*` }
      },
      {
        type: 'section',
        text: { type: 'mrkdwn', text: `*🎯 매체 목표* 매칭율 *${matchRate236}%* | 수익률 *${rateLabel236}* / 목표 *${fmt(targetCpa236)}원*\n*🔵 META* 광고비 *${fmt(meta236.totalSpend)}원* / 구매수 *${fmt(purchases236Meta)}건* / CPA *${fmt(cpa236Meta)}원*\n*🎵 TikTok* 광고비 *${fmt(tiktok236.totalSpend)}원* / 구매수 *${fmt(purchases236Tiktok)}건* / CPA *${fmt(cpa236Tiktok)}원*` }
      },
    ];

    // ── 단백질쉐이크 226+238 (getProduct226Split이 두 상품 합산 집계) ──
    const snapshot226 = loadSnapshot(targetDate);
    const rev226Total = split226.baseRevenue;
    const adSpend226Total = meta226.totalSpend + tiktok226.totalSpend;
    const purchases226Total = meta226.totalPurchases + tiktok226.totalPurchases;
    const matchedSingle = [...PROTEIN_CONFIG.단일수익률구간].reverse().find(g => targetDate >= g.from);
    const useSingleRate = !!matchedSingle;

    let protein226Blocks;
    let profit226Summary = 0;
    let summary226;

    if (snapshot226) {
      const revBait = snapshot226.cafe24.baseRevenue;
      const adBaitMeta = snapshot226.meta.totalSpend;
      const adBaitTiktok = snapshot226.tiktok.totalSpend;
      const adBait = adBaitMeta + adBaitTiktok;
      const purchasesBaitMeta = snapshot226.meta.totalPurchases;
      const purchasesBaitTiktok = snapshot226.tiktok.totalPurchases;
      const purchasesBait = purchasesBaitMeta + purchasesBaitTiktok;
      const ordersBait = snapshot226.cafe24.totalOrders;
      const rateBait = snapshot226.beforeRate || PROTEIN_CONFIG.미끼수익률;
      const rateLabelBait = `${(rateBait * 100).toFixed(2)}%`;
      const profitBait = Math.round(revBait / 1.1 * rateBait) - adBait;
      const avgBait = ordersBait > 0 ? Math.round(revBait / ordersBait) : 0;
      const matchBait = purchasesBait > 0 ? (ordersBait / purchasesBait * 100).toFixed(1) : '0.0';
      const targetCpaBait = purchasesBait > 0 ? Math.round((revBait / 1.1 * rateBait) / purchasesBait) : 0;
      const cpaBaitMeta = purchasesBaitMeta > 0 ? Math.round(adBaitMeta / purchasesBaitMeta) : 0;
      const cpaBaitTiktok = purchasesBaitTiktok > 0 ? Math.round(adBaitTiktok / purchasesBaitTiktok) : 0;

      const revAfter = rev226Total - revBait;
      const adAfterMeta = meta226.totalSpend - adBaitMeta;
      const adAfterTiktok = tiktok226.totalSpend - adBaitTiktok;
      const adAfter = adAfterMeta + adAfterTiktok;
      const purchasesAfterMeta = meta226.totalPurchases - purchasesBaitMeta;
      const purchasesAfterTiktok = tiktok226.totalPurchases - purchasesBaitTiktok;
      const purchasesAfter = purchasesAfterMeta + purchasesAfterTiktok;
      const ordersAfter = split226.totalOrders - ordersBait;
      const snapSetCounts = snapshot226.cafe24.setCounts || {};
      const afterSetCounts = {};
      for (const [set, count] of Object.entries(split226.setCounts || {})) {
        afterSetCounts[set] = Math.max(0, (count || 0) - (snapSetCounts[set] || 0));
      }
      const { rate: rateAfter, label: rateLabelAfter } = calcWeightedRate(afterSetCounts, PROTEIN_CONFIG.품절이후수익률);
      const profitAfter = Math.round(revAfter / 1.1 * rateAfter) - adAfter;
      const avgAfter = ordersAfter > 0 ? Math.round(revAfter / ordersAfter) : 0;
      const matchAfter = purchasesAfter > 0 ? (ordersAfter / purchasesAfter * 100).toFixed(1) : '0.0';
      const targetCpaAfter = purchasesAfter > 0 ? Math.round((revAfter / 1.1 * rateAfter) / purchasesAfter) : 0;
      const cpaAfterMeta = purchasesAfterMeta > 0 ? Math.round(adAfterMeta / purchasesAfterMeta) : 0;
      const cpaAfterTiktok = purchasesAfterTiktok > 0 ? Math.round(adAfterTiktok / purchasesAfterTiktok) : 0;

      const totalProfit226 = profitBait + profitAfter;
      profit226Summary = totalProfit226;

      const totalOrders226 = split226.totalOrders;
      const avgOrderValue226Total = totalOrders226 > 0 ? Math.round(rev226Total / totalOrders226) : 0;
      const matchRateTotal = purchases226Total > 0 ? (totalOrders226 / purchases226Total * 100).toFixed(1) : '0.0';
      const targetCpaTotal = purchases226Total > 0 ? Math.round((totalProfit226 + adSpend226Total) / purchases226Total) : 0;

      summary226 = { label: '226 (변경 후 기준)', targetCpa: targetCpaAfter, metaCpa: cpaAfterMeta, tiktokSpend: adAfterTiktok, tiktokCpa: cpaAfterTiktok };

      protein226Blocks = [
        { type: 'section', text: { type: 'mrkdwn', text: `*▸ 전체 합산*` } },
        { type: 'section', text: { type: 'mrkdwn', text: `🏷️ 매출 *${fmt(rev226Total * 0.8)}원* | 손익 *${fmt(totalProfit226)}원* | 광고비 *${fmt(adSpend226Total)}원* | 구매 *${fmt(totalOrders226)}건* | 객단가 *${fmt(avgOrderValue226Total)}원*` } },
        { type: 'section', text: { type: 'mrkdwn', text: `*🎯 매체 목표* 매칭율 *${matchRateTotal}%* / 목표 *${fmt(targetCpaTotal)}원*\n*🔵 META* 광고비 *${fmt(meta226.totalSpend)}원* / 구매수 *${fmt(meta226.totalPurchases)}건* / CPA *${fmt(meta226.cpa)}원*\n*🎵 TikTok* 광고비 *${fmt(tiktok226.totalSpend)}원* / 구매수 *${fmt(tiktok226.totalPurchases)}건* / CPA *${fmt(tiktok226.cpa)}원*` } },
        { type: 'divider' },
        { type: 'section', text: { type: 'mrkdwn', text: `*▸ 변경 전 (00:00 ~ ${snapshot226.time})*` } },
        { type: 'section', text: { type: 'mrkdwn', text: `🏷️ 매출 *${fmt(revBait * 0.8)}원* | 손익 *${fmt(profitBait)}원* | 광고비 *${fmt(adBait)}원* | 구매 *${fmt(ordersBait)}건* | 객단가 *${fmt(avgBait)}원* | 수익률 *${rateLabelBait}*` } },
        { type: 'section', text: { type: 'mrkdwn', text: `*🎯 매체 목표* 매칭율 *${matchBait}%* | 수익률 *${rateLabelBait}* / 목표 *${fmt(targetCpaBait)}원*\n*🔵 META* 광고비 *${fmt(adBaitMeta)}원* / 구매수 *${fmt(purchasesBaitMeta)}건* / CPA *${fmt(cpaBaitMeta)}원*\n*🎵 TikTok* 광고비 *${fmt(adBaitTiktok)}원* / 구매수 *${fmt(purchasesBaitTiktok)}건* / CPA *${fmt(cpaBaitTiktok)}원*` } },
        { type: 'section', text: { type: 'mrkdwn', text: `*▸ 변경 후 (${snapshot226.time} ~)*` } },
        { type: 'section', text: { type: 'mrkdwn', text: `🏷️ 매출 *${fmt(revAfter * 0.8)}원* | 손익 *${fmt(profitAfter)}원* | 광고비 *${fmt(adAfter)}원* | 구매 *${fmt(ordersAfter)}건* | 객단가 *${fmt(avgAfter)}원* | 수익률 *${rateLabelAfter}*` } },
        { type: 'section', text: { type: 'mrkdwn', text: `*🎯 매체 목표* 매칭율 *${matchAfter}%* | 수익률 *${rateLabelAfter}* / 목표 *${fmt(targetCpaAfter)}원*\n*🔵 META* 광고비 *${fmt(adAfterMeta)}원* / 구매수 *${fmt(purchasesAfterMeta)}건* / CPA *${fmt(cpaAfterMeta)}원*\n*🎵 TikTok* 광고비 *${fmt(adAfterTiktok)}원* / 구매수 *${fmt(purchasesAfterTiktok)}건* / CPA *${fmt(cpaAfterTiktok)}원*` } },
      ];
    } else {
      const { rate: rate226, label: rateLabel226 } = calcWeightedRate(
        split226.setCounts,
        useSingleRate ? matchedSingle.rate : PROTEIN_CONFIG.미끼수익률
      );
      const profit226 = Math.round(rev226Total / 1.1 * rate226) - adSpend226Total;
      profit226Summary = profit226;

      const avgOrderValue226 = split226.totalOrders > 0 ? Math.round(rev226Total / split226.totalOrders) : 0;
      const matchRate226 = purchases226Total > 0 ? (split226.totalOrders / purchases226Total * 100).toFixed(1) : '0.0';
      const targetCpa226 = purchases226Total > 0 ? Math.round((rev226Total / 1.1 * rate226) / purchases226Total) : 0;

      summary226 = { label: '226', targetCpa: targetCpa226, metaCpa: meta226.cpa, tiktokSpend: tiktok226.totalSpend, tiktokCpa: tiktok226.cpa };

      protein226Blocks = [
        { type: 'section', text: { type: 'mrkdwn', text: `🏷️ 매출 *${fmt(rev226Total * 0.8)}원* | 손익 *${fmt(profit226)}원* | 광고비 *${fmt(adSpend226Total)}원* | 구매 *${fmt(split226.totalOrders)}건* | 객단가 *${fmt(avgOrderValue226)}원*` } },
        { type: 'section', text: { type: 'mrkdwn', text: `*🎯 매체 목표* 매칭율 *${matchRate226}%* | 수익률 *${rateLabel226}* / 목표 *${fmt(targetCpa226)}원*\n*🔵 META* 광고비 *${fmt(meta226.totalSpend)}원* / 구매수 *${fmt(meta226.totalPurchases)}건* / CPA *${fmt(meta226.cpa)}원*\n*🎵 TikTok* 광고비 *${fmt(tiktok226.totalSpend)}원* / 구매수 *${fmt(tiktok226.totalPurchases)}건* / CPA *${fmt(tiktok226.cpa)}원*` } },
      ];
    }

    // ── 단쉐 요약용 공통 값 (226 단독 — 990딜(235)은 판매 종료로 제거) ──
    const matchRate226All = purchases226Total > 0 ? (split226.totalOrders / purchases226Total * 100).toFixed(1) : '0.0';

    // ── 메인 요약 메시지 ──
    const linePopcorn = `▸ *팝콘* 목표 *${fmt(targetCpaA)}원* → META *${fmt(metaA.cpa)}원*${cpaGapLabel(targetCpaA, metaA.cpa)} | 매칭율 *${matchRateA}%*`;
    const line226 = `▸ *${summary226.label}* 목표 *${fmt(summary226.targetCpa)}원* → META *${fmt(summary226.metaCpa)}원*${cpaGapLabel(summary226.targetCpa, summary226.metaCpa)}${summary226.tiktokSpend > 0 ? ` · TikTok *${fmt(summary226.tiktokCpa)}원*${cpaGapLabel(summary226.targetCpa, summary226.tiktokCpa)}` : ''}`;
    const line236 = `▸ *블트깡(236)* 목표 *${fmt(targetCpa236)}원* → META *${fmt(cpa236Meta)}원*${cpaGapLabel(targetCpa236, cpa236Meta)}${purchases236Tiktok > 0 ? ` · TikTok *${fmt(cpa236Tiktok)}원*${cpaGapLabel(targetCpa236, cpa236Tiktok)}` : ''}`;

    const summaryBlocks = [
      { type: 'header', text: { type: 'plain_text', text: `📊 제과 손익 요약 (${targetDate})` } },
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: `🔸 *제과 총 현황* 손익 *${fmt(profit)}원* _(단쉐 제외)_\n💰 매출 *${fmt(totalRevenue)}원* | 광고비 *${fmt(totalAdSpend)}원*${extraCostA > 0 ? ' (알림톡 비용 반영)' : ''} | 구매 *${fmt(totalOrders)}건* | 객단가 *${fmt(avgOrderValue)}원*\n${linePopcorn}`,
        },
      },
      { type: 'divider' },
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: `🔹 *단백질쉐이크* 손익 *${fmt(profit226Summary)}원* _(매출 80% 반영)_\n🏷️ 매출 *${fmt(rev226Total * 0.8)}원* | 광고비 *${fmt(adSpend226Total)}원* | 구매 *${fmt(split226.totalOrders)}건* | 매칭율 *${matchRate226All}%*\n${line226}`,
        },
      },
      { type: 'divider' },
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: `🥓 *블랙트러플 하몽깡* 손익 *${fmt(profit236)}원*\n💰 매출 *${fmt(rev236)}원* | 광고비 *${fmt(adSpend236)}원* | 구매 *${fmt(orders236)}건* | 매칭율 *${matchRate236}%*\n${line236}`,
        },
      },
      { type: 'context', elements: [{ type: 'mrkdwn', text: '🧵 수익률 · 객단가 · 매체별 상세는 스레드 확인' }] },
      {
        type: 'actions',
        elements: [
          { type: 'button', text: { type: 'plain_text', text: '📱 모바일 대시보드', emoji: true }, url: DASHBOARD_URL, action_id: 'open_dashboard' },
        ],
      },
    ];

    // ── 상세 블록 그룹 (뷰별로 본문/스레드에 재조합) ──
    const spacerBlocks = [
      { type: 'section', text: { type: 'mrkdwn', text: ' ' } },
      { type: 'divider' },
      { type: 'section', text: { type: 'mrkdwn', text: ' ' } },
    ];
    const jegwaTotalDetailBlocks = [
      { type: 'context', elements: [{ type: 'mrkdwn', text: '🔸 제과 전체 (단쉐 제외)' }] },
      { type: 'header', text: { type: 'plain_text', text: `[제과 총 현황 (${targetDate})]` } },
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text: `💰 실매출 *${fmt(totalRevenue)}원* | 손익 *${fmt(profit)}원* | 광고비 *${fmt(totalAdSpend)}원*\n🛒 구매 *${fmt(totalOrders)}건* | 객단가 *${fmt(avgOrderValue)}원* | 수익률 *45%*`
        }
      },
      { type: 'divider' }, // 제과 총 현황과 각 제품 성과 사이 구분선
    ];
    const popcornDetailBlocks = [
      { type: 'section', text: { type: 'mrkdwn', text: `*▸ 팝콘 (135+161+239+255)*` } },
      {
        type: 'section',
        text: { type: 'mrkdwn', text: `🏷️ 매출 *${fmt(revA)}원* | 손익 *${fmt(profitA)}원* | 광고비 *${fmt(totalAdSpendA)}원*${extraCostA > 0 ? ' (알림톡 비용 반영)' : ''} | 구매 *${fmt(salesA.totalOrders)}건* | 객단가 *${fmt(avgOrderValueA)}원*` }
      },
      {
        type: 'section',
        text: { type: 'mrkdwn', text: `*🎯 META목표* 매칭율 *${matchRateA}%* | 수익률 *45%* / 목표 *${fmt(targetCpaA)}원*\n*🔵 META* 광고비 *${fmt(metaA.totalSpend)}원* / 구매수 *${fmt(metaA.totalPurchases)}건* / CPA *${fmt(metaA.cpa)}원*` }
      },
    ];
    const proteinDetailBlocks = [
      { type: 'context', elements: [{ type: 'mrkdwn', text: '🔹 단백질쉐이크 (매출의 80%만 반영)' }] },
      { type: 'header', text: { type: 'plain_text', text: `[단백질쉐이크 (226) (${targetDate})]` } },
      ...protein226Blocks,
    ];
    const bltDetailBlocks = [
      { type: 'header', text: { type: 'plain_text', text: `[블랙트러플 하몽깡 (${targetDate})]` } },
      ...bltkkang236Blocks,
    ];
    const threadNoticeBlock = { type: 'context', elements: [{ type: 'mrkdwn', text: '🧵 나머지 상품 상세는 스레드 확인' }] };
    const dashboardBlock = {
      type: 'actions',
      elements: [
        { type: 'button', text: { type: 'plain_text', text: '📱 모바일 대시보드', emoji: true }, url: DASHBOARD_URL, action_id: 'open_dashboard' },
      ],
    };

    // ── 뷰별 본문/스레드 조합 ──
    let mainText, mainBlocks, threadBlocks;
    if (view === '팝콘') {
      mainText = `팝콘 손익 현황 (${targetDate})`;
      mainBlocks = [...jegwaTotalDetailBlocks, ...popcornDetailBlocks, threadNoticeBlock, dashboardBlock];
      threadBlocks = [...proteinDetailBlocks, ...spacerBlocks, ...bltDetailBlocks];
    } else if (view === '블트하') {
      mainText = `블랙트러플 하몽깡 손익 현황 (${targetDate})`;
      mainBlocks = [...jegwaTotalDetailBlocks, ...bltDetailBlocks, threadNoticeBlock, dashboardBlock];
      threadBlocks = [...popcornDetailBlocks, ...spacerBlocks, ...proteinDetailBlocks];
    } else if (view === '단쉐') {
      mainText = `단백질쉐이크 손익 현황 (${targetDate})`;
      mainBlocks = [...proteinDetailBlocks, threadNoticeBlock, dashboardBlock];
      threadBlocks = [...jegwaTotalDetailBlocks, ...popcornDetailBlocks, ...spacerBlocks, ...bltDetailBlocks];
    } else {
      // 기존 /손익확인_제과: 요약 본문 + 전체 상세 스레드
      mainText = `제과 손익 요약 (${targetDate})`;
      mainBlocks = summaryBlocks;
      threadBlocks = [...jegwaTotalDetailBlocks, ...popcornDetailBlocks, ...spacerBlocks, ...proteinDetailBlocks, ...spacerBlocks, ...bltDetailBlocks];
    }

    await client.chat.update({ channel, ts: loading.ts, text: mainText, blocks: mainBlocks });
    await client.chat.postMessage({ channel, thread_ts: threadTs || loading.ts, text: `손익 상세 (${targetDate})`, blocks: threadBlocks });
  } catch (err) {
    const detail = err.response?.data ? JSON.stringify(err.response.data) : err.message;
    const isTokenError = detail.includes('invalid_grant') || detail.includes('invalid_token');
    console.error('손익확인_제과 오류:', detail);
    await client.chat.update({
      channel,
      ts: loading.ts,
      text: isTokenError ? TOKEN_ERROR_MSG : `❌ 데이터 조회 중 오류가 발생했습니다: ${detail}`
    });
  }
}

function register(slackApp) {
  slackApp.command('/손익확인_제과', async ({ ack, body, client }) => {
    await ack();
    const { date } = getNow();
    await handleJegwaCheck(client, body.channel_id, body.thread_ts, date);
  });

  slackApp.command('/손익확인_제과_전일', async ({ ack, body, client }) => {
    await ack();
    await handleJegwaCheck(client, body.channel_id, body.thread_ts, getYesterdayKST());
  });

  slackApp.action('open_dashboard', async ({ ack }) => {
    await ack();
  });

  // ── 상품별 손익확인 (당일) — 본문에 해당 상품 상세, 나머지 상품은 스레드 ──
  // ⚠️ Slack 앱 설정(api.slack.com > Slash Commands)에 아래 3개 커맨드를 등록해야 동작함
  slackApp.command('/손익확인_팝콘', async ({ ack, body, client }) => {
    await ack();
    const { date } = getNow();
    await handleJegwaCheck(client, body.channel_id, body.thread_ts, date, '팝콘');
  });

  slackApp.command('/손익확인_단쉐', async ({ ack, body, client }) => {
    await ack();
    const { date } = getNow();
    await handleJegwaCheck(client, body.channel_id, body.thread_ts, date, '단쉐');
  });

  slackApp.command('/손익확인_블트하', async ({ ack, body, client }) => {
    await ack();
    const { date } = getNow();
    await handleJegwaCheck(client, body.channel_id, body.thread_ts, date, '블트하');
  });

  slackApp.command('/단백질쉐이크_품절해제', async ({ ack, body, client }) => {
    await ack();
    const messenger = makeMessenger(client, body.channel_id, body.thread_ts);
    const success = clearSnapshot();
    await messenger.post({
      text: success ? '✅ 품절 해제 완료. 이후 손익확인 시 49% 단일 적용됩니다.' : '❌ 해제 실패 (저장된 스냅샷이 없거나 오류 발생)'
    });
  });

  slackApp.command('/단백질쉐이크_품절', async ({ ack, body, client }) => {
    await ack();
    const messenger = makeMessenger(client, body.channel_id, body.thread_ts);
    const { date, time } = getNow();
    await messenger.post({ text: '⏳ 품절 시점 스냅샷 저장 중...' });
    try {
      const [meta226, tiktok226, split226] = await Promise.all([
        metaService.getMetaStats('단백질쉐이크', date, '990'),
        tiktokService.getAdStats('단백질쉐이크', date, date),
        cafe24Service.getProduct226Split({ startDate: date, endDate: date }),
      ]);
      const snapSetCounts = split226.setCounts || {};
      const { rate: beforeRate } = calcWeightedRate(snapSetCounts, PROTEIN_CONFIG.미끼수익률);
      const snapshot = {
        date,
        time,
        beforeRate,
        meta: { totalSpend: meta226.totalSpend, totalPurchases: meta226.totalPurchases, cpa: meta226.cpa },
        tiktok: { totalSpend: tiktok226.totalSpend, totalPurchases: tiktok226.totalPurchases, cpa: tiktok226.cpa },
        cafe24: {
          baseRevenue: split226.baseRevenue,
          totalOrders: split226.totalOrders,
          almondRevenue: split226.almondRevenue,
          almondOrders: split226.almondOrders,
          setCounts: split226.setCounts,
        },
      };
      saveSnapshot(snapshot);
      const fmt = n => Math.round(n).toLocaleString('ko-KR');
      await messenger.update({
        text: `✅ 품절 스냅샷 저장 완료 (${date} ${time})\nMETA *${fmt(meta226.totalSpend)}원* / TikTok *${fmt(tiktok226.totalSpend)}원* / 매출 *${fmt(split226.baseRevenue)}원* / 주문 *${split226.totalOrders}건*`
      });
    } catch (err) {
      const detail = err.response?.data ? JSON.stringify(err.response.data) : err.message;
      await messenger.update({ text: `❌ 스냅샷 저장 실패: ${detail}` });
    }
  });

  slackApp.command('/자사몰_주문수_제과_전일', async ({ ack, body, client }) => {
    await ack();
    const messenger = makeMessenger(client, body.channel_id, body.thread_ts);
    const now = new Date();
    const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
    const dayOfWeek = kst.getDay();
    const DAY_NAMES = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];

    let dates = [];
    if (dayOfWeek === 1) {
      for (let i = 3; i >= 1; i--) {
        const d = new Date(kst);
        d.setDate(d.getDate() - i);
        dates.push(d.toISOString().slice(0, 10));
      }
    } else {
      dates.push(getYesterdayKST());
    }

    await messenger.post({ text: `⏳ 주문 수량 현황 조회 중... (${dates.join(', ')})` });
    try {
      for (const date of dates) {
        const DAY_EMOJIS = { '금요일': '🟡', '토요일': '🔵', '일요일': '🔴' };
        const dayName = DAY_NAMES[new Date(date + 'T12:00:00').getDay()];
        const emoji = DAY_EMOJIS[dayName] || '📅';
        const results = await getDistribution(cafe24Service, date);
        const blocks = buildDistributionBlocks(results, `${date} ${dayName}`);
        await client.chat.postMessage({ channel: body.channel_id, text: `━━━━━━━━━━━━━━━━━━━━━━\n${emoji} 자사몰 주문 수량 현황 (${date} ${dayName})\n━━━━━━━━━━━━━━━━━━━━━━`, blocks });
      }
      await messenger.update({ text: `✅ 조회 완료 (${dates.join(', ')})` });
    } catch (err) {
      const detail = err.response?.data ? JSON.stringify(err.response.data) : err.message;
      await messenger.update({ text: `❌ 오류가 발생했습니다: ${detail}` });
    }
  });

  slackApp.command('/자사몰_주문수_제과_당일', async ({ ack, body, client }) => {
    await ack();
    const messenger = makeMessenger(client, body.channel_id, body.thread_ts);
    const { date } = getNow();
    const DAY_NAMES = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];
    const DAY_EMOJIS = { '금요일': '🟡', '토요일': '🔵', '일요일': '🔴' };
    const dayName = DAY_NAMES[new Date(date + 'T12:00:00').getDay()];
    const emoji = DAY_EMOJIS[dayName] || '📅';

    await messenger.post({ text: `⏳ 주문 수량 현황 조회 중... (${date})` });
    try {
      const results = await getDistribution(cafe24Service, date);
      const blocks = buildDistributionBlocks(results, `${date} ${dayName}`);
      await client.chat.postMessage({
        channel: body.channel_id,
        text: `━━━━━━━━━━━━━━━━━━━━━━\n${emoji} 자사몰 주문 수량 현황 (${date} ${dayName})\n━━━━━━━━━━━━━━━━━━━━━━`,
        blocks,
      });
      await messenger.update({ text: `✅ 조회 완료 (${date})` });
    } catch (err) {
      const detail = err.response?.data ? JSON.stringify(err.response.data) : err.message;
      await messenger.update({ text: `❌ 오류가 발생했습니다: ${detail}` });
    }
  });

  slackApp.command('/자사몰_주문수_빙과_전일', async ({ ack, body, client }) => {
    await ack();
    const messenger = makeMessenger(client, body.channel_id, body.thread_ts);
    const yesterday = getYesterdayKST();
    await messenger.post({ text: `⏳ 빙과 주문 수량 현황 조회 중... (${yesterday})` });
    try {
      const results = await getDistribution(cafe24Service, yesterday, [195, 210]);
      const blocks = buildDistributionBlocks(results, yesterday);
      await messenger.update({ text: `빙과 주문 수량 현황 (${yesterday})`, blocks });
    } catch (err) {
      const detail = err.response?.data ? JSON.stringify(err.response.data) : err.message;
      await messenger.update({ text: `❌ 오류가 발생했습니다: ${detail}` });
    }
  });
}

module.exports = { register, PROFIT_RATES, PROTEIN_CONFIG };
