"""Trendbox UI theme: CSS tokens and injection helpers."""

from __future__ import annotations

import streamlit as st

# Warm off-white page canvas (replaces flat #FFFFFF app background).
CANVAS_BG = "#F2F1E9"

# ── Master stylesheet ─────────────────────────────────────────────────────────

LABELBOX_CSS = """
<style>
:root {
  --tb-canvas: __CANVAS_BG__;
  --tb-surface: #FFFFFF;
  --tb-ink: #111827;
  --tb-muted: #6B7280;
  --tb-subtle: #9CA3AF;
  --tb-border: #E5E7EB;
  --tb-accent: #E8622A;
  --tb-radius: 10px;
  --tb-radius-sm: 8px;
  --tb-space-2: 8px;
  --tb-space-3: 12px;
  --tb-space-4: 16px;
  --tb-space-5: 24px;
  --tb-space-6: 32px;
  --tb-max-width: 1240px;
}

/* ── Page canvas ── */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main,
.block-container {
  background-color: var(--tb-canvas) !important;
}

/* ── Streamlit chrome ── */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }
[data-testid="stSidebar"]               { display: none; }
[data-testid="stSidebarCollapsedControl"]{ display: none; }
[data-testid="collapsedControl"]         { display: none; }

/* ── Layout ── */
* { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }

.block-container {
  padding-top:    0    !important;
  padding-left:   var(--tb-space-6) !important;
  padding-right:  var(--tb-space-6) !important;
  padding-bottom: 96px !important;
  max-width: var(--tb-max-width) !important;
  margin-left: auto !important;
  margin-right: auto !important;
}

@media (max-width: 768px) {
  .block-container {
    padding-left: var(--tb-space-4) !important;
    padding-right: var(--tb-space-4) !important;
  }
}

/* ── Typography & page structure (Stripe / Linear pattern) ── */
.tb-page-header {
  margin-bottom: var(--tb-space-5);
  padding-bottom: var(--tb-space-4);
  border-bottom: 1px solid var(--tb-border);
}
.tb-page-eyebrow {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--tb-subtle);
  margin-bottom: 6px;
}
.tb-page-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--tb-ink);
  letter-spacing: -0.4px;
  line-height: 1.2;
  margin: 0 0 6px 0;
}
.tb-page-subtitle {
  font-size: 15px;
  color: var(--tb-muted);
  line-height: 1.55;
  margin: 0;
  max-width: 640px;
}
.tb-page-meta {
  font-size: 12px;
  color: var(--tb-subtle);
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.tb-section {
  margin-bottom: var(--tb-space-5);
}
.tb-section-header {
  margin-bottom: var(--tb-space-4);
}
.tb-section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--tb-ink);
  margin: 0 0 4px 0;
  letter-spacing: -0.2px;
}
.tb-section-desc {
  font-size: 13px;
  color: var(--tb-muted);
  line-height: 1.5;
  margin: 0;
}
.tb-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--tb-space-3);
  margin-bottom: var(--tb-space-4);
  padding: var(--tb-space-3) 0;
}
.tb-divider {
  border: none;
  border-top: 1px solid var(--tb-border);
  margin: var(--tb-space-5) 0;
}
.tb-kpi-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0;
  padding: var(--tb-space-4) var(--tb-space-5);
  background: var(--tb-surface);
  border: 1px solid var(--tb-border);
  border-radius: var(--tb-radius);
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.tb-kpi-footer .stat-item {
  font-size: 13px;
  color: var(--tb-muted);
  padding: 0 20px;
}
.tb-kpi-footer .stat-item:first-child { padding-left: 0; }
.tb-kpi-footer .stat-item strong { color: var(--tb-ink); font-weight: 600; }
.tb-kpi-footer .stat-sep {
  width: 1px;
  height: 16px;
  background: var(--tb-border);
  flex-shrink: 0;
}
.tb-action-panel {
  background: var(--tb-surface);
  border: 1px solid var(--tb-border);
  border-radius: var(--tb-radius);
  padding: var(--tb-space-4) var(--tb-space-5);
  margin-top: var(--tb-space-5);
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.tb-empty-state {
  text-align: center;
  padding: 56px var(--tb-space-5);
  max-width: 480px;
  margin: 48px auto;
}
.home-stat-status {
  font-size: 18px;
  font-weight: 600;
  color: #059669;
  display: flex;
  align-items: center;
  gap: 8px;
  line-height: 1;
  margin-bottom: 12px;
}
.home-stat-status.offline { color: #DC2626; }
.online-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  background: #10B981;
  box-shadow: 0 0 0 3px rgba(16,185,129,0.2);
  animation: pulse-dot 2s ease infinite;
}
.offline-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  background: #EF4444;
}
@keyframes pulse-dot {
  0%,100% { box-shadow: 0 0 0 3px rgba(16,185,129,0.20); }
  50%      { box-shadow: 0 0 0 7px rgba(16,185,129,0.07); }
}
.action-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--tb-ink);
  margin-bottom: 6px;
}
.action-desc {
  font-size: 13px;
  color: var(--tb-muted);
  margin-bottom: var(--tb-space-4);
  line-height: 1.55;
}
.action-meta {
  font-size: 12px;
  color: var(--tb-subtle);
  margin-top: var(--tb-space-2);
}
.st-key-btn_dashboard button {
  background: #111827 !important;
  color: #FFFFFF !important;
  border: none !important;
  font-weight: 600 !important;
}
.st-key-btn_dashboard button:hover {
  background: #374151 !important;
}

/* ── Top bar ── */
.topbar {
  background: var(--tb-canvas);
  border-bottom: 1px solid #E5E7EB;
  padding: 10px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.topbar-brand .brand-name {
  font-size: 15px;
  font-weight: 700;
  color: #111827;
}
.topbar-brand .brand-sep {
  font-size: 15px;
  color: #9CA3AF;
}
.topbar-ts {
  font-size: 11px;
  color: #9CA3AF;
  text-align: right;
  padding-top: 2px;
}

/* ── Radio as pill tabs ── */
[data-testid="stRadio"] > label { display: none; }
[data-testid="stRadio"] [role="radiogroup"] {
  flex-direction: row !important;
  gap: 2px;
  background: #F3F4F6;
  border-radius: 8px;
  padding: 3px;
  border: 1px solid #E5E7EB;
  display: inline-flex;
}
[data-testid="stRadio"] label {
  border-radius: 6px !important;
  padding: 5px 14px !important;
  cursor: pointer;
  margin: 0 !important;
}
[data-testid="stRadio"] label p {
  font-size: 13px !important;
  font-weight: 500 !important;
  color: #6B7280 !important;
  margin: 0 !important;
  white-space: nowrap;
}
[data-testid="stRadio"] label:has(input:checked) {
  background: #111827 !important;
}
[data-testid="stRadio"] label:has(input:checked) p {
  color: #FFFFFF !important;
  font-weight: 600 !important;
}
[data-testid="stRadio"] input { display: none !important; }
/* Hide the radio-dot circle so tabs read as pure pills */
[data-testid="stRadio"] [role="radiogroup"] label > div:first-child { display: none !important; }

/* ── Cards ── */
.lb-card {
  background: var(--tb-surface);
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 20px 24px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  margin-bottom: 16px;
}

/* Override Streamlit bordered container to match lb-card */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--tb-surface) !important;
  border: 1px solid var(--tb-border) !important;
  border-radius: var(--tb-radius) !important;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
  padding: 20px 24px !important;
}

/* ── Metric display (label above number) ── */
.lb-metric-label {
  font-size: 11px;
  font-weight: 500;
  color: #6B7280;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.lb-metric-value {
  font-size: 32px;
  font-weight: 700;
  color: #111827;
  line-height: 1;
  margin-bottom: 12px;
}
.lb-metric-value.amber { color: #D97706; }

/* ── Confidence badges ── */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}
.badge-high   { background: #D1FAE5; color: #065F46; }
.badge-medium { background: #FEF3C7; color: #92400E; }
.badge-low    { background: #FEE2E2; color: #991B1B; }

/* ── Tags ── */
.tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  margin-right: 6px;
}
.tag-brand  { background: #DBEAFE; color: #1E40AF; }
.tag-weight { background: #F3F4F6; color: #374151; }
.tag-kind-fresh   { background: #D1FAE5; color: #065F46; }
.tag-kind-branded { background: #EDE9FE; color: #5B21B6; }
.tag-kind-unknown { background: #F3F4F6; color: #6B7280; }
.source-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.source-stage0 { background: #ECFDF5; color: #047857; }
.source-ml     { background: #EFF6FF; color: #1D4ED8; }

/* ── Animations ── */
@keyframes name-flash {
  0%   { opacity: 0.15; transform: translateY(6px); }
  100% { opacity: 1;    transform: translateY(0);   }
}
.product-name-animate {
  animation: name-flash 0.35s ease-out 1 both;
}

@keyframes shimmer {
  0%   { background-position:  200% 0; }
  100% { background-position: -200% 0; }
}
.skeleton-line {
  background: linear-gradient(
    90deg,
    #F3F4F6 25%,
    #E5E7EB 50%,
    #F3F4F6 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: 6px;
}

/* ── Suggestion cards ── */
.suggestion-card {
  background: var(--tb-surface);
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  padding: 14px 16px;
  margin-bottom: 10px;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}
.suggestion-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.09);
}
.suggestion-high   { border-left: 3px solid #10B981; }
.suggestion-medium { border-left: 3px solid #F59E0B; }
.suggestion-low    { border-left: 3px solid #EF4444; }

/* ── Alive micro-animations (visual only — no workflow changes) ── */
@keyframes cardSlideIn {
  from { opacity: 0; transform: translateY(10px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes tagPop {
  0%   { transform: scale(0.85); opacity: 0; }
  70%  { transform: scale(1.04); }
  100% { transform: scale(1); opacity: 1; }
}
@keyframes pendingPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245,158,11,0.0); }
  50%       { box-shadow: 0 0 0 4px rgba(245,158,11,0.22); }
}
@keyframes progressGlow {
  0%, 100% { filter: brightness(1); }
  50%       { filter: brightness(1.15); }
}
.alive-card-pending {
  animation: pendingPulse 2.4s ease-in-out infinite;
  border-radius: 8px;
}
.tag { animation: tagPop 0.35s ease-out both; }
.lb-progress-fill { animation: progressGlow 2s ease-in-out infinite; }

/* ── Section labels ── */
.section-label {
  font-size: 11px;
  font-weight: 600;
  color: #9CA3AF;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 12px;
}

/* ── Progress bar (custom, 4px) ── */
.lb-progress-track {
  background: #F3F4F6;
  border-radius: 4px;
  height: 4px;
  overflow: hidden;
}
.lb-progress-fill {
  background: #3B82F6;
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

/* ── Filter bar ── */
.lb-filter-bar {
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  padding: 8px 16px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.lb-filter-pill {
  font-size: 13px;
  color: #374151;
  font-weight: 500;
  cursor: pointer;
}

/* ── Table ── */
.lb-table-header {
  font-size: 11px;
  font-weight: 600;
  color: #6B7280;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 8px 12px;
  border-bottom: 1px solid #E5E7EB;
  background: #F9FAFB;
}
.lb-table-row {
  padding: 10px 12px;
  border-bottom: 1px solid #F3F4F6;
  font-size: 13px;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 8px;
}
.lb-table-row:nth-child(even) { background: #FAFAFA; }
.lb-table-total {
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 700;
  color: #111827;
  background: #F9FAFB;
  border-top: 1px solid #E5E7EB;
}
.lb-pagination {
  font-size: 12px;
  color: #6B7280;
  padding: 8px 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

/* ── Action bar (fixed bottom) ── */
.action-bar-spacer { height: 20px; }

/* Target the last block of the main content as sticky footer */
section[data-testid="stMain"] > .stMainBlockContainer > div > [data-testid="stVerticalBlock"] > div:last-child > [data-testid="stVerticalBlock"] {
  position: sticky;
  bottom: 0;
  background: var(--tb-canvas);
  border-top: 1px solid #E5E7EB;
  padding: 12px 0 !important;
  z-index: 100;
  margin-top: 8px;
}

/* ── Buttons ── */
/* Approve: solid dark */
[data-testid="stButton"][key="approve_top"] button,
.st-key-approve_top button {
  background: #111827 !important;
  color: #FFFFFF !important;
  border: none !important;
  font-weight: 600 !important;
}
.st-key-approve_top button:hover {
  background: #374151 !important;
  box-shadow: 0 0 0 3px rgba(17,24,39,0.18) !important;
}

/* Reject: red outline */
.st-key-reject_all button {
  background: #FFFFFF !important;
  color: #DC2626 !important;
  border: 1px solid #DC2626 !important;
  font-weight: 600 !important;
}
.st-key-reject_all button:hover {
  background: #FEE2E2 !important;
  color: #DC2626 !important;
}

/* ── Offline banner ── */
.offline-banner {
  background: #FFFBEB;
  border: 1px solid #FDE68A;
  border-left: 3px solid #F59E0B;
  border-radius: 6px;
  padding: 12px 16px;
  color: #92400E;
  font-size: 13px;
  margin-bottom: 16px;
}

/* ── Updated badge (top right) ── */
.updated-badge {
  font-size: 11px;
  color: #9CA3AF;
  text-align: right;
}

/* ── Streamlit native adjustments ── */
div[data-testid="stHorizontalBlock"] { gap: 8px; }
[data-testid="stTextInput"] > div { border-radius: 6px !important; }
div[data-baseweb="input"] { border-radius: 6px !important; }

/* Remove Streamlit default metric styling */
[data-testid="stMetric"] { background: transparent !important; border: none !important; padding: 0 !important; }
[data-testid="stMetricValue"] { font-size: 32px !important; font-weight: 700 !important; color: #111827 !important; }
[data-testid="stMetricLabel"] { font-size: 11px !important; font-weight: 500 !important; color: #6B7280 !important; text-transform: uppercase !important; letter-spacing: 0.06em !important; }

/* ── Page entrance animation ─────────────────────────────────────────────── */
/* Targets the content block, not the outer shell, so it fires on navigation
   but NOT on every Streamlit rerun (React diffs keep the container alive). */
[data-testid="stMain"] .block-container {
  animation: pageIn 0.22s ease-out both;
}
@keyframes pageIn {
  from { opacity: 0; transform: translateY(5px); }
  to   { opacity: 1; transform: translateY(0);   }
}

/* ── Live indicator dot ─────────────────────────────────────────────────── */
.live-dot {
  width: 6px; height: 6px;
  background: #10B981; border-radius: 50%;
  display: inline-block;
  vertical-align: middle; margin-right: 4px;
  animation: livePulse 2s ease infinite;
}
@keyframes livePulse {
  0%, 100% { opacity: 1;    transform: scale(1);    }
  50%       { opacity: 0.4; transform: scale(0.72); }
}

/* ── Approve flash micro-animation ──────────────────────────────────────── */
@keyframes approveFlash {
  0%   { background: rgba(16,185,129,0.15);
         border-color: #10B981 !important;
         box-shadow: 0 0 0 3px rgba(16,185,129,0.20); }
  65%  { background: rgba(16,185,129,0.05); border-color: #10B981; }
  100% { background: var(--tb-surface); border-color: #E5E7EB;
         box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
}
.card-flash-approve {
  animation: approveFlash 0.5s ease-out 1 forwards;
}

/* ── Confidence mini-bar grow animation ─────────────────────────────────── */
@keyframes barGrow {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}
</style>
"""

# Hover lift + motion for Home & Review only (not Analytics).
ALIVE_INTERACTION_CSS = """
<style>
/* ── Nav row — lift the whole dark strip on approach ── */
div[data-testid="stHorizontalBlock"]:has([class*="st-key-nav_"]) {
  transition: box-shadow 0.28s ease, transform 0.28s cubic-bezier(.34,1.2,.64,1) !important;
}
div[data-testid="stHorizontalBlock"]:has([class*="st-key-nav_"]):hover {
  box-shadow: 0 10px 32px rgba(17,24,39,0.32) !important;
  transform: translateY(-2px);
}
/* Inactive nav tabs — pop on hover */
[class*="st-key-nav_go_"] button {
  transition: background 0.2s ease, color 0.2s ease,
              transform 0.22s cubic-bezier(.34,1.3,.64,1),
              box-shadow 0.22s ease !important;
}
[class*="st-key-nav_go_"] button:hover:not(:disabled) {
  background: #4B5563 !important;
  color: #FFFFFF !important;
  transform: translateY(-3px) scale(1.05) !important;
  box-shadow: 0 8px 20px rgba(0,0,0,0.35) !important;
  border: none !important;
}
[class*="st-key-nav_go_"] button:active:not(:disabled) {
  transform: translateY(-1px) scale(1.02) !important;
}
.st-key-nav_go_logo button:hover:not(:disabled) {
  transform: translateY(-3px) scale(1.08) !important;
  box-shadow: 0 8px 22px rgba(232,98,42,0.55) !important;
  filter: brightness(1.08);
}
/* Active tab — subtle glow when the bar is hovered */
[class*="st-key-nav_active_"] button {
  transition: box-shadow 0.22s ease, transform 0.22s ease !important;
}
div[data-testid="stHorizontalBlock"]:has([class*="st-key-nav_"]):hover
  [class*="st-key-nav_active_"] button {
  box-shadow: 0 4px 14px rgba(255,255,255,0.22) !important;
  transform: scale(1.02);
}

/* ── Bordered Streamlit cards ── */
[data-testid="stVerticalBlockBorderWrapper"] {
  transition: transform 0.24s cubic-bezier(.34,1.2,.64,1),
              box-shadow 0.24s ease,
              border-color 0.2s ease !important;
  will-change: transform;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
  transform: translateY(-5px) scale(1.008) !important;
  box-shadow: 0 14px 36px rgba(17,24,39,0.13),
              0 4px 10px rgba(17,24,39,0.06) !important;
  border-color: #D1D5DB !important;
}

/* ── HTML lb-cards (product panel, progress, history tables) ── */
.lb-card {
  transition: transform 0.24s cubic-bezier(.34,1.2,.64,1),
              box-shadow 0.24s ease,
              border-color 0.2s ease;
}
.lb-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(17,24,39,0.11);
  border-color: #D1D5DB;
}

/* ── Review pill tabs ── */
[data-testid="stRadio"] label {
  transition: transform 0.18s ease, background 0.18s ease, box-shadow 0.18s ease !important;
}
[data-testid="stRadio"] label:not(:has(input:checked)):hover {
  transform: translateY(-2px) !important;
  background: #E5E7EB !important;
  box-shadow: 0 3px 10px rgba(17,24,39,0.08) !important;
}
[data-testid="stRadio"] label:not(:has(input:checked)):hover p {
  color: #374151 !important;
}

/* ── Suggestion cards — deeper lift ── */
.suggestion-card:hover {
  transform: translateY(-4px) scale(1.01) !important;
  box-shadow: 0 10px 24px rgba(17,24,39,0.12) !important;
  border-color: #D1D5DB !important;
}

/* ── History / decision table rows ── */
.decision-row {
  transition: background 0.15s ease, transform 0.18s ease, box-shadow 0.18s ease !important;
}
.decision-row:hover {
  transform: translateX(4px) !important;
  box-shadow: -4px 0 0 rgba(17,24,39,0.06) !important;
}

/* ── Buttons (action cards, select, approve/reject) — not nav ── */
.stButton:not([class*="st-key-nav_"]) button {
  transition: transform 0.18s cubic-bezier(.34,1.2,.64,1),
              box-shadow 0.18s ease,
              background 0.15s ease,
              border-color 0.15s ease !important;
}
.stButton:not([class*="st-key-nav_"]) button:hover:not(:disabled) {
  transform: translateY(-2px) !important;
  box-shadow: 0 5px 16px rgba(17,24,39,0.14) !important;
}
.stButton:not([class*="st-key-nav_"]) button:active:not(:disabled) {
  transform: translateY(0) scale(0.98) !important;
}

/* ── Home stats footer row ── */
.stats-row .stat-item {
  transition: transform 0.18s ease, color 0.18s ease;
  border-radius: 6px;
  cursor: default;
}
.stats-row .stat-item:hover {
  transform: translateY(-3px);
  color: #374151;
}
.stats-row .stat-item:hover strong {
  color: #111827;
}

/* ── Live / updated badge ── */
.updated-badge {
  transition: transform 0.2s ease, opacity 0.2s ease;
  display: inline-flex;
  align-items: center;
}
.updated-badge:hover {
  transform: scale(1.04);
  opacity: 0.92;
}

/* ── Tags on product card ── */
.tag:hover {
  transform: scale(1.06);
  transition: transform 0.15s ease;
}
</style>
"""




def inject_styles() -> None:
    """Inject the Labelbox-style CSS into the current Streamlit page."""
    st.markdown(LABELBOX_CSS.replace("__CANVAS_BG__", CANVAS_BG), unsafe_allow_html=True)


def inject_alive_interactions() -> None:
    """Inject hover lift/motion CSS — use on Home & Review only, not Analytics."""
    st.markdown(ALIVE_INTERACTION_CSS, unsafe_allow_html=True)

