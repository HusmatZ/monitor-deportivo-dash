# app.py
import dash
from dash import dcc, html, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from db import init_db

# --- vistas de INICIO separadas ---
from views.athlete.home_view import layout as athlete_home_layout, register_callbacks as register_athlete_home_callbacks
from views.coach.home_view import layout as coach_home_layout, register_callbacks as register_coach_home_callbacks

# --- vistas del ATLETA (pestañas) ---
from views.athlete.monitor_view import layout as monitor_layout, register_callbacks as register_monitor_callbacks
from views.athlete.questionnaire_view import layout as questionnaire_layout_view, register_callbacks as register_questionnaire_callbacks
from views.athlete.routines_view import layout as routines_layout
from views.athlete.progress_view import layout as progress_layout

# --- auth (modales + callbacks de login/registro) ---
from auth import register_auth_callbacks

# Inicializar app Dash con estilos de Bootstrap
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)
server = app.server

# --- INYECTAR CSS ---
app.index_string = """
<!DOCTYPE html>
<html>
  <head>
    {%metas%}
    <title>AXISFIT</title>
    {%favicon%}
    {%css%}
    <style>
      :root{
        --c-navbar:#eef2f6;
        --c-bg:#eef2f6;
        --c-surface:#c2ccd9;
        --c-card:#ffffff;
        --c-border:#d1d9e3;
        --c-text:#0f172a;
        --c-muted:#475569;
        --c-accent:#3a6ea5;
        --c-accent-2:#5b8bd6;

        /* gris oscuro del texto de los botones */
        --btn-dark-gray:#334155;

        /* alturas principales de la ventana */
        --navbar-h: 10vh;        /* espacio superior / navbar */
        --footer-h: 15vh;        /* cuadro del footer */
        --main-content-h: calc(100vh - var(--navbar-h) - var(--footer-h)); /* cuadro gris */

        --navbar-pad-x: clamp(12px, 1.6vw, 24px);
        --navbar-gap: clamp(8px, 1vw, 16px);
        --navbar-logo-h: clamp(44px, 7vh, 68px);
        --navbar-btn-h: clamp(36px, 4.6vh, 48px);
        --navbar-btn-font: clamp(12px, 1vw, 15px);
        --navbar-auth-btn-w: clamp(138px, 14vw, 200px);
        --navbar-center-btn-w: clamp(120px, 11vw, 170px);
      }

      html{ overflow:hidden; }
      body{ background:var(--c-bg); color:var(--c-text); overflow:hidden; }
      body.modal-open{ padding-right:0 !important; }
      .modal{ overflow-y:auto !important; }

      .navbar-custom{
        background: var(--c-navbar) !important;
        border-bottom: 1px solid var(--c-border);
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        overflow: visible !important;
        height: var(--navbar-h) !important;
        min-height: var(--navbar-h) !important;
        max-height: var(--navbar-h) !important;
      }

      .navbar-custom .container-fluid{
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        padding-left: var(--navbar-pad-x) !important;
        padding-right: var(--navbar-pad-x) !important;
        flex-wrap: nowrap !important;
        overflow: visible !important;
        height: 100% !important;
        min-height: 100% !important;
        max-height: 100% !important;
      }

      .navbar-inner{
        display:flex !important;
        align-items:center !important;
        justify-content:space-between !important;
        flex-wrap:nowrap !important;
        position:relative !important;
        gap: var(--navbar-gap);
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        overflow: visible !important;
        width: 100% !important;
        height: 100% !important;
        min-height: 100% !important;
        max-height: 100% !important;
      }

      .navbar-spacer{
        height: var(--navbar-h);
        min-height: var(--navbar-h);
        max-height: var(--navbar-h);
        flex: 0 0 var(--navbar-h);
      }

      #logo-btn{
        height: 100% !important;
        display:flex !important;
        align-items:center !important;
      }

      #logo-btn img{
        height: var(--navbar-logo-h) !important;
        max-height: calc(var(--navbar-h) - 12px) !important;
        width: auto !important;
        max-width: min(18vw, 220px) !important;
      }

      .btn-nav{
        background: var(--c-navbar) !important;
        color: var(--btn-dark-gray) !important;
        border: 1px solid transparent !important;
        width: var(--navbar-center-btn-w);
        min-width: 0;
        height: var(--navbar-btn-h) !important;
        min-height: var(--navbar-btn-h) !important;
        padding: 0 clamp(10px, 1vw, 14px) !important;
        box-shadow:none !important;
        font-size: var(--navbar-btn-font) !important;
        font-weight:400 !important;
        font-family: inherit !important;
        transition: all .15s ease !important;
      }
      .btn-nav:hover{
        background: var(--btn-dark-gray) !important;
        color:#fff !important;
        border-color: var(--btn-dark-gray) !important;
        transform: none !important;
      }
      .btn-nav:active{
        background:#1f2937 !important;
        color:#fff !important;
        border-color:#1f2937 !important;
        transform: none !important;
      }

      .modal-content{ background:var(--c-card); border:1px solid var(--c-border); }
      .page-shell{
        width: 100%;
        max-width: 100%;
        height: var(--main-content-h);
        min-height: var(--main-content-h);
        max-height: var(--main-content-h);
        padding-left: 12px;
        padding-right: 12px;
        box-sizing:border-box;
        overflow:hidden;
      }
      #main-content{
        width:100%;
        height:100%;
        min-height:0;
        max-height:100%;
        overflow:hidden;
      }
      .surface{
        background:var(--c-surface);
        border-radius:12px;
        padding:0px 24px 24px 24px;
        height:100%;
        min-height:0;
        max-height:100%;
        width:100%;
        max-width:100%;
        display:block;
        box-sizing:border-box;
        overflow:auto;
      }
      .ax-monitor-surface{
        height:100% !important;
        min-height:0 !important;
        max-height:100% !important;
      }

      .surface.ax-monitor-surface,
      .surface.ax-questionnaire-surface{
        --axisfit-view-title-h:clamp(64px, 7.5vh, 82px);
        display:flex !important;
        flex-direction:column !important;
        height:100% !important;
        min-height:0 !important;
        max-height:100% !important;
        padding-top:0 !important;
        padding-right:0 !important;
        padding-bottom:0 !important;
        padding-left:0 !important;
        overflow:hidden !important;
        box-sizing:border-box !important;
      }

      .surface.ax-monitor-surface > .ax-monitor-title-row,
      .surface.ax-questionnaire-surface > .ax-monitor-title-row{
        width:100% !important;
        flex:0 0 var(--axisfit-view-title-h) !important;
        height:var(--axisfit-view-title-h) !important;
        min-height:var(--axisfit-view-title-h) !important;
        max-height:var(--axisfit-view-title-h) !important;
        margin-top:0 !important;
        margin-right:0 !important;
        margin-bottom:8px !important;
        margin-left:0 !important;
        padding:0 !important;
        display:flex !important;
        align-items:flex-start !important;
        justify-content:space-between !important;
        gap:12px !important;
        flex-wrap:wrap !important;
        box-sizing:border-box !important;
      }

      .surface.ax-monitor-surface > .ax-monitor-title-row > .ax-title-banner,
      .surface.ax-questionnaire-surface > .ax-monitor-title-row > .ax-title-banner{
        width:75% !important;
        min-width:0 !important;
        max-width:75% !important;
        height:100% !important;
        min-height:0 !important;
        background:#0b1220 !important;
        border-top-left-radius:0 !important;
        border-top-right-radius:0 !important;
        border-bottom-left-radius:12px !important;
        border-bottom-right-radius:12px !important;
        box-shadow:inset 0 0 0 1px rgba(255,255,255,.04) !important;
        padding-top:10px !important;
        padding-right:clamp(8px, 1vw, 12px) !important;
        padding-bottom:10px !important;
        padding-left:clamp(8px, 1vw, 12px) !important;
        display:flex !important;
        align-items:flex-end !important;
        box-sizing:border-box !important;
      }

      .surface.ax-monitor-surface > .ax-monitor-title-row > .ax-title-banner > .ax-page-title,
      .surface.ax-questionnaire-surface > .ax-monitor-title-row > .ax-title-banner > .ax-page-title{
        display:block !important;
        color:#ffffff !important;
        margin:0 !important;
        padding:0 !important;
        font-size:clamp(20px, 2.1vw, 32px) !important;
        font-weight:500 !important;
        line-height:1.15 !important;
        letter-spacing:0 !important;
        white-space:normal !important;
      }

      .surface.ax-monitor-surface > .ax-monitor-body,
      .surface.ax-questionnaire-surface > .ax-questionnaire-body{
        flex:1 1 calc(100% - var(--axisfit-view-title-h) - 8px) !important;
        height:calc(100% - var(--axisfit-view-title-h) - 8px) !important;
        min-height:0 !important;
        max-height:calc(100% - var(--axisfit-view-title-h) - 8px) !important;
        margin:0 !important;
        gap:8px !important;
        row-gap:8px !important;
        column-gap:8px !important;
        overflow:hidden !important;
        box-sizing:border-box !important;
      }

      @media (max-width: 1200px){
        .surface.ax-monitor-surface,
        .surface.ax-questionnaire-surface{
          height:auto !important;
          min-height:calc(100vh - var(--navbar-h) - 16px) !important;
          max-height:none !important;
          padding-top:12px !important;
          padding-bottom:24px !important;
          overflow:visible !important;
        }

        .surface.ax-monitor-surface > .ax-monitor-title-row,
        .surface.ax-questionnaire-surface > .ax-monitor-title-row,
        .surface.ax-monitor-surface > .ax-monitor-body,
        .surface.ax-questionnaire-surface > .ax-questionnaire-body{
          flex:0 0 auto !important;
          height:auto !important;
          max-height:none !important;
          overflow:visible !important;
        }
      }

      @media (max-width: 768px){
        .surface.ax-monitor-surface,
        .surface.ax-questionnaire-surface{
          padding-top:10px !important;
          padding-bottom:16px !important;
        }

        .surface.ax-monitor-surface > .ax-monitor-title-row > .ax-title-banner,
        .surface.ax-questionnaire-surface > .ax-monitor-title-row > .ax-title-banner{
          width:100% !important;
          max-width:100% !important;
        }
      }

      #main-content > .surface.ax-monitor-surface,
      #main-content > .surface.ax-questionnaire-surface,
      #main-content > .surface.ax-routines-surface,
      #main-content > .surface.ax-progress-surface{
        --axisfit-view-title-h:clamp(64px, 7.5vh, 82px);
        display:flex !important;
        flex-direction:column !important;
        height:100% !important;
        min-height:0 !important;
        max-height:100% !important;
        padding-top:0 !important;
        padding-right:0 !important;
        padding-bottom:0 !important;
        padding-left:0 !important;
        overflow:hidden !important;
        box-sizing:border-box !important;
      }

      #main-content > .surface.ax-monitor-surface > .ax-monitor-title-row,
      #main-content > .surface.ax-questionnaire-surface > .ax-monitor-title-row,
      #main-content > .surface.ax-routines-surface > .ax-monitor-title-row,
      #main-content > .surface.ax-progress-surface > .ax-monitor-title-row{
        width:100% !important;
        flex:0 0 var(--axisfit-view-title-h) !important;
        height:var(--axisfit-view-title-h) !important;
        min-height:var(--axisfit-view-title-h) !important;
        max-height:var(--axisfit-view-title-h) !important;
        margin:0 0 8px 0 !important;
        padding:0 !important;
        display:flex !important;
        align-items:flex-start !important;
        justify-content:space-between !important;
        gap:12px !important;
        flex-wrap:wrap !important;
        box-sizing:border-box !important;
      }

      #main-content > .surface.ax-monitor-surface > .ax-monitor-title-row > .ax-title-banner,
      #main-content > .surface.ax-questionnaire-surface > .ax-monitor-title-row > .ax-title-banner,
      #main-content > .surface.ax-routines-surface > .ax-monitor-title-row > .ax-title-banner,
      #main-content > .surface.ax-progress-surface > .ax-monitor-title-row > .ax-title-banner{
        width:75% !important;
        min-width:0 !important;
        max-width:75% !important;
        height:100% !important;
        min-height:0 !important;
        background:#0b1220 !important;
        border-top-left-radius:0 !important;
        border-top-right-radius:0 !important;
        border-bottom-left-radius:12px !important;
        border-bottom-right-radius:12px !important;
        box-shadow:inset 0 0 0 1px rgba(255,255,255,.04) !important;
        padding-top:10px !important;
        padding-right:clamp(8px, 1vw, 12px) !important;
        padding-bottom:10px !important;
        padding-left:clamp(8px, 1vw, 12px) !important;
        display:flex !important;
        align-items:flex-end !important;
        box-sizing:border-box !important;
      }

      #main-content > .surface.ax-monitor-surface > .ax-monitor-title-row > .ax-title-banner > .ax-page-title,
      #main-content > .surface.ax-questionnaire-surface > .ax-monitor-title-row > .ax-title-banner > .ax-page-title,
      #main-content > .surface.ax-routines-surface > .ax-monitor-title-row > .ax-title-banner > .ax-page-title,
      #main-content > .surface.ax-progress-surface > .ax-monitor-title-row > .ax-title-banner > .ax-page-title{
        display:block !important;
        color:#ffffff !important;
        margin:0 !important;
        padding:0 !important;
        font-size:clamp(20px, 2.1vw, 32px) !important;
        font-weight:500 !important;
        line-height:1.15 !important;
        letter-spacing:0 !important;
        white-space:normal !important;
      }

      #main-content > .surface.ax-monitor-surface > .ax-monitor-body,
      #main-content > .surface.ax-questionnaire-surface > .ax-questionnaire-body,
      #main-content > .surface.ax-routines-surface > .ax-routines-body,
      #main-content > .surface.ax-progress-surface > .ax-progress-body{
        flex:1 1 calc(100% - var(--axisfit-view-title-h) - 8px) !important;
        height:calc(100% - var(--axisfit-view-title-h) - 8px) !important;
        min-height:0 !important;
        max-height:calc(100% - var(--axisfit-view-title-h) - 8px) !important;
        margin:0 !important;
        gap:8px !important;
        row-gap:8px !important;
        column-gap:8px !important;
        box-sizing:border-box !important;
      }

      #main-content > .surface.ax-routines-surface > .ax-routines-body,
      #main-content > .surface.ax-progress-surface > .ax-progress-body{
        overflow:auto !important;
      }

      @media (max-width: 1200px){
        #main-content > .surface.ax-monitor-surface,
        #main-content > .surface.ax-questionnaire-surface,
        #main-content > .surface.ax-routines-surface,
        #main-content > .surface.ax-progress-surface{
          height:auto !important;
          min-height:calc(100vh - var(--navbar-h) - 16px) !important;
          max-height:none !important;
          padding-top:12px !important;
          padding-bottom:24px !important;
          overflow:visible !important;
        }

        #main-content > .surface.ax-monitor-surface > .ax-monitor-title-row,
        #main-content > .surface.ax-questionnaire-surface > .ax-monitor-title-row,
        #main-content > .surface.ax-routines-surface > .ax-monitor-title-row,
        #main-content > .surface.ax-progress-surface > .ax-monitor-title-row,
        #main-content > .surface.ax-monitor-surface > .ax-monitor-body,
        #main-content > .surface.ax-questionnaire-surface > .ax-questionnaire-body,
        #main-content > .surface.ax-routines-surface > .ax-routines-body,
        #main-content > .surface.ax-progress-surface > .ax-progress-body{
          flex:0 0 auto !important;
          height:auto !important;
          max-height:none !important;
          overflow:visible !important;
        }
      }

      @media (max-width: 768px){
        #main-content > .surface.ax-monitor-surface,
        #main-content > .surface.ax-questionnaire-surface,
        #main-content > .surface.ax-routines-surface,
        #main-content > .surface.ax-progress-surface{
          padding-top:10px !important;
          padding-bottom:16px !important;
        }

        #main-content > .surface.ax-monitor-surface > .ax-monitor-title-row > .ax-title-banner,
        #main-content > .surface.ax-questionnaire-surface > .ax-monitor-title-row > .ax-title-banner,
        #main-content > .surface.ax-routines-surface > .ax-monitor-title-row > .ax-title-banner,
        #main-content > .surface.ax-progress-surface > .ax-monitor-title-row > .ax-title-banner{
          width:100% !important;
          max-width:100% !important;
        }
      }

      #ath-home-root.surface{
        box-sizing:border-box;
        padding-top:24px !important;
        padding-right:24px !important;
        padding-bottom:24px !important;
        padding-left:24px !important;
      }

      #ath-home-root > .row.g-3{
        --bs-gutter-x:8px;
        --bs-gutter-y:8px;
        margin-top:0 !important;
      }

      @media (max-width:1200px){
        #ath-home-root.surface{
          padding-top:12px !important;
          padding-right:24px !important;
          padding-bottom:24px !important;
          padding-left:24px !important;
        }
      }

      @media (max-width:768px){
        #ath-home-root.surface{
          padding-top:10px !important;
          padding-right:12px !important;
          padding-bottom:16px !important;
          padding-left:12px !important;
        }
      }

      .soft-hr{ border-top:1px solid var(--c-border); }
      h2,h3{ color:var(--c-text); }
      .muted{ color:var(--c-muted); }
      .req::after { content:" *"; color:#b91c1c; }
      .help{ font-size:.875rem; color:var(--c-muted); }

      /* ==========================================================
         AXISFIT LANDING PÚBLICA
         ========================================================== */
      .ax-public-landing-surface{
        height:100% !important;
        min-height:0 !important;
        max-height:100% !important;
        overflow:auto !important;
        padding:24px !important;
        background:var(--c-surface) !important;
      }
      .ax-public-landing{
        width:100%;
        min-width:0;
        display:flex;
        flex-direction:column;
        gap:16px;
        color:#e2e8f0;
      }
      .ax-landing-hero{
        display:grid;
        grid-template-columns:minmax(0, 1.05fr) minmax(320px, .95fr);
        gap:16px;
        align-items:stretch;
        min-width:0;
      }
      .ax-landing-hero-card,
      .ax-landing-section-card{
        background:
          radial-gradient(circle at 12% 18%, rgba(59,130,246,.16), transparent 30%),
          linear-gradient(135deg, #0b1220 0%, #101827 52%, #111827 100%);
        border-radius:16px;
        box-shadow:
          inset 0 0 0 1px rgba(255,255,255,.06),
          0 12px 28px rgba(15,23,42,.12);
        padding:clamp(16px, 2vw, 28px);
        min-width:0;
      }
      .ax-landing-hero-card{
        display:flex;
        flex-direction:column;
        justify-content:center;
        gap:14px;
      }
      .ax-landing-kicker{
        display:inline-flex;
        align-items:center;
        width:max-content;
        max-width:100%;
        padding:6px 10px;
        border-radius:999px;
        color:#dbeafe;
        background:rgba(59,130,246,.14);
        box-shadow:inset 0 0 0 1px rgba(147,197,253,.14);
        font-size:clamp(10px, .84vw, 13px);
        font-weight:700;
        line-height:1.15;
      }
      .ax-landing-brand-title{
        margin:0;
        color:#fff;
        font-family:Georgia,'Times New Roman',Times,serif;
        font-size:clamp(28px, 3.2vw, 52px);
        font-weight:800;
        line-height:1;
        letter-spacing:.035em;
        text-transform:uppercase;
        text-shadow:0 1px 0 rgba(255,255,255,.26),0 0 12px rgba(255,255,255,.10);
      }
      .ax-landing-headline{
        margin:0;
        color:#fff;
        font-size:clamp(24px, 3vw, 44px);
        font-weight:800;
        line-height:1.05;
        letter-spacing:-.02em;
        max-width:860px;
      }
      .ax-landing-subtitle{
        margin:0;
        color:rgba(226,232,240,.78);
        font-size:clamp(12px, 1.05vw, 16px);
        font-weight:500;
        line-height:1.45;
        max-width:780px;
      }
      .ax-landing-actions{
        display:flex;
        align-items:center;
        gap:10px;
        flex-wrap:wrap;
        margin-top:2px;
      }
      .ax-landing-actions .btn{
        min-width:clamp(140px, 12vw, 190px) !important;
      }
      .ax-landing-trust-row{
        display:flex;
        gap:8px;
        flex-wrap:wrap;
        margin-top:2px;
      }
      .ax-landing-mockup{
        display:flex;
        flex-direction:column;
        gap:10px;
        min-width:0;
        height:100%;
      }
      .ax-landing-mockup-top{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:10px;
      }
      .ax-landing-mockup-grid{
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:10px;
        min-width:0;
      }
      .ax-landing-mockup-panel{
        background:rgba(2,6,23,.78);
        border-radius:12px;
        box-shadow:inset 0 0 0 1px rgba(255,255,255,.08);
        padding:12px;
        min-width:0;
      }
      .ax-landing-gauge{
        --landing-score:76;
        width:clamp(78px, 7vw, 108px);
        aspect-ratio:1/1;
        border-radius:50%;
        background:conic-gradient(#22c55e calc(var(--landing-score) * 1%), rgba(255,255,255,.10) 0);
        display:grid;
        place-items:center;
        margin:auto;
        box-shadow:0 0 0 1px rgba(255,255,255,.08),0 12px 22px rgba(0,0,0,.22);
      }
      .ax-landing-gauge::before{
        content:'76';
        width:72%;
        aspect-ratio:1/1;
        border-radius:50%;
        background:#0b1220;
        display:grid;
        place-items:center;
        color:#fff;
        font-size:clamp(22px, 2vw, 30px);
        font-weight:800;
      }
      .ax-landing-bar{
        width:100%;
        height:8px;
        border-radius:999px;
        background:rgba(255,255,255,.10);
        overflow:hidden;
        box-shadow:inset 0 0 0 1px rgba(255,255,255,.08);
      }
      .ax-landing-bar > span{
        display:block;
        height:100%;
        width:32%;
        border-radius:999px;
        background:linear-gradient(90deg,#22c55e,rgba(34,197,94,.55));
      }
      .ax-landing-mini-chart{
        height:80px;
        border-radius:10px;
        background:
          linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.02)),
          repeating-linear-gradient(90deg,rgba(226,232,240,.08) 0 1px,transparent 1px 34px),
          repeating-linear-gradient(0deg,rgba(226,232,240,.08) 0 1px,transparent 1px 20px);
        position:relative;
        overflow:hidden;
      }
      .ax-landing-mini-chart::after{
        content:'';
        position:absolute;
        left:0;
        right:0;
        top:38px;
        height:3px;
        background:linear-gradient(90deg,transparent,#3b82f6,#22c55e,transparent);
        transform:skewY(-7deg);
        box-shadow:0 0 16px rgba(59,130,246,.35);
      }
      .ax-landing-section-card{
        display:flex;
        flex-direction:column;
        gap:12px;
      }
      .ax-landing-section-header{
        display:flex;
        flex-direction:column;
        gap:4px;
        max-width:780px;
      }
      .ax-landing-section-title{
        color:#fff;
        margin:0;
        font-size:clamp(18px, 1.8vw, 28px);
        font-weight:800;
        line-height:1.12;
      }
      .ax-landing-section-subtitle{
        color:rgba(226,232,240,.72);
        margin:0;
        font-size:clamp(11px, .95vw, 14px);
        font-weight:500;
        line-height:1.4;
      }
      .ax-landing-benefits-grid,
      .ax-landing-steps-grid,
      .ax-landing-modules-grid,
      .ax-landing-proof-grid{
        display:grid;
        grid-template-columns:repeat(4, minmax(0, 1fr));
        gap:10px;
      }
      .ax-landing-item-card{
        background:rgba(2,6,23,.78);
        border-radius:12px;
        box-shadow:inset 0 0 0 1px rgba(255,255,255,.08);
        padding:12px;
        display:flex;
        flex-direction:column;
        gap:8px;
        min-width:0;
      }
      .ax-landing-icon-dot{
        width:34px;
        height:34px;
        border-radius:999px;
        display:inline-flex;
        align-items:center;
        justify-content:center;
        color:#dbeafe;
        font-size:13px;
        font-weight:800;
        background:rgba(59,130,246,.16);
        box-shadow:inset 0 0 0 1px rgba(147,197,253,.16);
      }
      .ax-landing-item-title{
        color:#fff;
        font-size:clamp(12px, .95vw, 16px);
        font-weight:800;
        line-height:1.15;
        margin:0;
      }
      .ax-landing-item-text{
        color:rgba(226,232,240,.72);
        font-size:clamp(10px, .84vw, 13px);
        font-weight:500;
        line-height:1.35;
        margin:0;
      }
      .ax-landing-final-cta{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:16px;
        flex-wrap:wrap;
      }
      .ax-landing-final-cta > div:first-child{
        flex:1 1 420px;
        min-width:0;
      }
      @media (max-width:1200px){
        .ax-landing-hero{
          grid-template-columns:1fr;
        }
        .ax-landing-benefits-grid,
        .ax-landing-steps-grid,
        .ax-landing-modules-grid,
        .ax-landing-proof-grid{
          grid-template-columns:repeat(2,minmax(0,1fr));
        }
      }
      @media (max-width:768px){
        .ax-public-landing-surface{
          padding:10px 12px !important;
        }
        .ax-public-landing{
          gap:12px;
        }
        .ax-landing-hero-card,
        .ax-landing-section-card{
          padding:14px;
          border-radius:14px;
        }
        .ax-landing-mockup-grid,
        .ax-landing-benefits-grid,
        .ax-landing-steps-grid,
        .ax-landing-modules-grid,
        .ax-landing-proof-grid{
          grid-template-columns:1fr;
        }
        .ax-landing-actions,
        .ax-landing-final-cta{
          align-items:stretch;
          flex-direction:column;
        }
        .ax-landing-actions .btn,
        .ax-landing-final-cta .btn{
          width:100% !important;
          min-width:0 !important;
        }
      }

      /* ==========================================================
         AXISFIT FOOTER GLOBAL
         ========================================================== */
      .ax-footer-shell{
        width:100%;
        max-width:100%;
        height:var(--footer-h);
        min-height:var(--footer-h);
        max-height:var(--footer-h);
        padding-left:12px;
        padding-right:12px;
        box-sizing:border-box;
        overflow:hidden;
      }

      .ax-axisfit-footer{
        width:100%;
        height:calc(100% - 16px);
        min-height:0;
        max-height:calc(100% - 16px);
        margin-top:8px;
        margin-bottom:8px;
        color:#e2e8f0;
        font-family:inherit;
        font-size:clamp(10px, .78vw, 12px);
        font-weight:400;
        background:
          radial-gradient(circle at 12% 18%, rgba(59,130,246,.18), transparent 28%),
          linear-gradient(135deg, #0b1220 0%, #101827 52%, #111827 100%);
        border-radius:16px;
        box-shadow:
          inset 0 0 0 1px rgba(255,255,255,.07),
          0 10px 24px rgba(15,23,42,.14);
        padding:clamp(6px, .75vw, 10px);
        overflow:hidden;
        box-sizing:border-box;
        display:flex;
        flex-direction:column;
        justify-content:space-between;
      }

      .ax-axisfit-footer-top{
        display:grid;
        grid-template-columns:minmax(0, 1.25fr) minmax(0, .95fr) minmax(0, .95fr) minmax(0, .70fr);
        gap:clamp(8px, 1.1vw, 16px);
        align-items:center;
        width:100%;
        min-height:0;
      }

      .ax-axisfit-footer-brand,
      .ax-axisfit-footer-col{
        display:flex;
        flex-direction:column;
        min-width:0;
        font-family:inherit;
        font-size:clamp(10px, .78vw, 12px);
        font-weight:400;
      }

      .ax-axisfit-footer-brand{ gap:5px; }
      .ax-axisfit-footer-col{ gap:5px; }

      .ax-axisfit-footer-logo{
        color:#ffffff !important;
        font-family:Georgia, 'Times New Roman', Times, serif !important;
        font-size:clamp(20px, 1.65vw, 25px) !important;
        font-weight:800 !important;
        line-height:1.05 !important;
        letter-spacing:.035em !important;
        text-transform:uppercase !important;
        margin:0 !important;
        padding:0 !important;
        text-decoration:none !important;
        text-shadow:0 1px 0 rgba(255,255,255,.26), 0 0 8px rgba(255,255,255,.12);
      }

      .ax-axisfit-footer-tagline,
      .ax-axisfit-footer-link,
      .ax-axisfit-footer-text,
      .ax-axisfit-footer-mini-badge,
      .ax-axisfit-footer-disclaimer,
      .ax-axisfit-footer-copy,
      .ax-axisfit-footer-social{
        font-family:inherit !important;
        font-size:clamp(8px, .78vw, 10px) !important;
        font-weight:400 !important;
        letter-spacing:0 !important;
        text-transform:none !important;
      }

      .ax-axisfit-footer-tagline{
        color:rgba(226,232,240,.78);
        line-height:1.25;
        max-width:460px;
        margin:0;
      }

      .ax-axisfit-footer-mini-badges,
      .ax-axisfit-footer-socials{
        display:flex;
        flex-wrap:wrap;
        gap:8px;
      }

      .ax-axisfit-footer-follow-col{
        align-items:flex-start;
      }

      .ax-axisfit-footer-follow-card{
        display:flex;
        align-items:center;
        justify-content:flex-start;
        gap:8px;
        padding:6px 8px;
        border-radius:14px;
        background:rgba(255,255,255,.055);
        box-shadow:inset 0 0 0 1px rgba(255,255,255,.075);
      }

      .ax-axisfit-footer-mini-badge{
        display:inline-flex;
        align-items:center;
        justify-content:center;
        padding:3px 7px;
        border-radius:999px;
        color:#dbeafe;
        background:rgba(59,130,246,.14);
        box-shadow:inset 0 0 0 1px rgba(147,197,253,.14);
        line-height:1.15;
        white-space:nowrap;
      }

      .ax-axisfit-footer-title{
        color:#ffffff;
        font-family:inherit !important;
        font-size:clamp(10px, .78vw, 12px) !important;
        font-weight:700 !important;
        line-height:1.2;
        margin:0 0 2px 0;
        letter-spacing:0 !important;
        text-transform:none !important;
      }

      .ax-axisfit-footer-link,
      .ax-axisfit-footer-text{
        color:rgba(226,232,240,.76);
        line-height:1.25;
        text-decoration:none;
        margin:0;
        transition:color .16s ease, transform .16s ease;
      }

      .ax-axisfit-footer-link:hover{
        color:#ffffff;
        text-decoration:none;
        transform:translateX(2px);
      }

      .ax-axisfit-footer-contact-card{
        display:flex;
        flex-direction:column;
        align-items:flex-start;
        gap:4px;
        padding:0;
        border-radius:0;
        background:transparent;
        box-shadow:none;
      }

      .ax-axisfit-footer-contact-list{
        display:flex;
        flex-direction:column;
        align-items:flex-start;
        gap:4px;
        width:100%;
        min-width:0;
      }

      .ax-axisfit-footer-two-col-grid{
        display:grid;
        grid-template-columns:repeat(2, minmax(0, 1fr));
        column-gap:12px;
        row-gap:4px;
        align-items:center;
        width:100%;
      }

      .ax-axisfit-footer-two-col-grid .ax-axisfit-footer-link,
      .ax-axisfit-footer-two-col-grid .ax-axisfit-footer-text{
        min-width:0;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
      }

      .ax-axisfit-footer-bottom{
        margin-top:4px;
        padding-top:4px;
        border-top:1px solid rgba(255,255,255,.10);
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
        flex-wrap:wrap;
      }

      .ax-axisfit-footer-disclaimer{
        flex:1 1 520px;
        color:rgba(226,232,240,.70);
        line-height:1.2;
        margin:0;
      }

      .ax-axisfit-footer-copy{
        flex:0 0 auto;
        color:rgba(226,232,240,.76);
        line-height:1.35;
        margin:0;
        white-space:nowrap;
      }

      .ax-axisfit-footer-social{
        width:26px;
        height:26px;
        border-radius:999px;
        display:inline-flex;
        align-items:center;
        justify-content:center;
        color:#e2e8f0;
        background:rgba(255,255,255,.08);
        box-shadow:inset 0 0 0 1px rgba(255,255,255,.10);
        text-decoration:none;
        line-height:1;
        transition:background .16s ease, color .16s ease, transform .16s ease;
      }

      .ax-axisfit-footer-social:hover{
        color:#ffffff;
        background:rgba(59,130,246,.28);
        transform:translateY(-1px);
        text-decoration:none;
      }

      @media (max-width:1200px){
        .ax-axisfit-footer-top{
          grid-template-columns:repeat(2, minmax(0, 1fr));
        }
      }

      @media (max-width:768px){
        .ax-axisfit-footer{
          margin-top:8px;
          border-radius:14px;
          padding:8px;
        }

        .ax-axisfit-footer-top{
          grid-template-columns:1fr;
          gap:12px;
        }

        .ax-axisfit-footer-two-col-grid{
          grid-template-columns:1fr;
        }

        .ax-axisfit-footer-bottom{
          align-items:flex-start;
          flex-direction:column;
        }

        .ax-axisfit-footer-copy{
          white-space:normal;
        }
      }

      #navbar-auth{
        display:flex !important;
        flex-direction:row !important;
        flex-wrap:nowrap !important;
        align-items:center !important;
        gap: 8px !important;
        white-space: nowrap !important;
      }
      #navbar-auth > *{
        display:flex !important;
        flex-direction:row !important;
        flex-wrap:nowrap !important;
        align-items:center !important;
        gap: 8px !important;
        white-space: nowrap !important;
      }
      #navbar-auth .btn-group,
      #navbar-auth .btn-group-vertical,
      #navbar-auth .vstack,
      #navbar-auth .d-grid{
        display:flex !important;
        flex-direction:row !important;
        flex-wrap:nowrap !important;
        align-items:center !important;
        gap: 8px !important;
      }
      #navbar-auth .row{
        flex-wrap: nowrap !important;
        --bs-gutter-x: .5rem;
        --bs-gutter-y: 0;
        margin: 0 !important;
      }
      #navbar-auth .col,
      #navbar-auth [class*="col-"]{
        flex: 0 0 auto !important;
        width: auto !important;
        max-width: none !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
      }
      #navbar-auth .btn{
        display:inline-flex !important;
        align-items:center !important;
        justify-content:center !important;
        align-self:center !important;
        min-height: var(--navbar-btn-h) !important;
        height: var(--navbar-btn-h) !important;
        padding: 0 clamp(10px, 1vw, 14px) !important;
        line-height: 1.2 !important;
        flex: 0 1 auto !important;
        width: var(--navbar-auth-btn-w) !important;
        max-width: 100% !important;
        white-space: nowrap !important;
        margin: 0 !important;
        transition: all .15s ease !important;
        font-weight:400 !important;
        font-size: var(--navbar-btn-font) !important;
      }

      #navbar-auth [id*="register"]{ order: 0 !important; }
      #navbar-auth [id*="login"]{ order: 1 !important; }

      #navbar-auth [id*="login"]{
        background:#000 !important;
        color:#fff !important;
        border:1px solid #000 !important;
        font-weight:400 !important;
      }
      #navbar-auth [id*="login"]:hover{
        background:#2b2b2b !important;
        border-color:#2b2b2b !important;
        color:#fff !important;
      }
      #navbar-auth [id*="login"]:active{
        background:#111 !important;
        border-color:#111 !important;
      }

      #navbar-auth [id*="register"]{
        background: var(--c-navbar) !important;
        color: var(--c-text) !important;
        border: 1px solid transparent !important;
        box-shadow: none !important;
        font-weight:400 !important;
      }
      #navbar-auth [id*="register"]:hover{
        background:#000 !important;
        color:#fff !important;
        border-color:#000 !important;
      }
      #navbar-auth [id*="register"]:active{
        background:#111 !important;
        border-color:#111 !important;
        color:#fff !important;
      }

      #access-login{
        background:#000 !important;
        color:#fff !important;
        border:1px solid #000 !important;
        font-weight:400 !important;
        transition: all .15s ease !important;
      }
      #access-login:hover{
        background:#2b2b2b !important;
        border-color:#2b2b2b !important;
        color:#fff !important;
      }
      #access-login:active{
        background:#111 !important;
        border-color:#111 !important;
      }

      #access-register{
        background: var(--c-navbar) !important;
        color: var(--c-text) !important;
        border: 1px solid transparent !important;
        box-shadow: none !important;
        font-weight:400 !important;
        transition: all .15s ease !important;
      }
      #access-register:hover{
        background:#000 !important;
        color:#fff !important;
        border-color:#000 !important;
      }
      #access-register:active{
        background:#111 !important;
        border-color:#111 !important;
        color:#fff !important;
      }

      #navbar-center{
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        gap: clamp(6px, .8vw, 12px);
        max-width: 52vw;
        overflow: hidden;
      }

      @media (max-width: 1200px){
        #navbar-center{
          max-width: 48vw;
        }
      }

      @media (max-width: 992px){
        .navbar-custom{
          height: auto !important;
          min-height: var(--navbar-h) !important;
          max-height: none !important;
        }

        .navbar-custom .container-fluid,
        .navbar-inner{
          height: auto !important;
          min-height: var(--navbar-h) !important;
          max-height: none !important;
        }

        #navbar-center{
          display: none !important;
        }

        #navbar-auth .btn{
          width: auto !important;
          min-width: clamp(118px, 24vw, 170px) !important;
        }
      }

      #navbar-auth .dropdown-toggle,
      #navbar-auth .dropdown-toggle.btn,
      #navbar-auth .btn.ax-user-menu-toggle{
        width: 40px !important;
        min-width: 40px !important;
        max-width: 40px !important;
        height: 40px !important;
        min-height: 40px !important;
        max-height: 40px !important;
        padding: 0 !important;
        border-radius: 50% !important;
        flex: 0 0 40px !important;
        aspect-ratio: 1 / 1;
      }

      @media (max-width: 768px){
        :root{
          --navbar-h: 10vh;
          --navbar-logo-h: clamp(38px, 6.2vh, 52px);
          --navbar-btn-h: clamp(34px, 4.2vh, 42px);
          --navbar-auth-btn-w: auto;
        }

        .navbar-custom .container-fluid{
          padding-left: 12px !important;
          padding-right: 12px !important;
        }

        .page-shell{
          height:var(--main-content-h);
          min-height:var(--main-content-h);
          max-height:var(--main-content-h);
          padding-left: 8px;
          padding-right: 8px;
        }

        .surface{
          width: 100%;
          max-width: 100%;
        }

        #navbar-auth{
          gap: 6px !important;
        }

        #navbar-auth .btn{
          min-width: 112px !important;
          padding-left: 10px !important;
          padding-right: 10px !important;
          font-size: 12px !important;
        }

        #navbar-auth .dropdown-toggle,
        #navbar-auth .dropdown-toggle.btn,
        #navbar-auth .btn.ax-user-menu-toggle{
          min-width: 38px !important;
          max-width: 38px !important;
          width: 38px !important;
          min-height: 38px !important;
          max-height: 38px !important;
          height: 38px !important;
          flex: 0 0 38px !important;
          padding: 0 !important;
        }
      }
    </style>
  </head>
  <body>
    {%app_entry%}
    <footer>
      {%config%}
      {%scripts%}
      {%renderer%}
    </footer>
  </body>
</html>
"""

# Inicializar la base de datos
init_db()


def axisfit_public_landing():
    """Landing pública mostrada antes de iniciar sesión."""
    benefit_items = [
        ("01", "Detecta compensaciones", "Identifica diferencias entre zona torácica y lumbar para corregir patrones antes de que afecten tu técnica."),
        ("02", "Mejora tu postura", "Visualiza estado general, inclinación, estabilidad y alertas durante tus sesiones."),
        ("03", "Entrena con datos", "Conecta rutinas, cuestionarios y sesiones para entender cómo evoluciona tu rendimiento."),
        ("04", "Sigue tu progreso", "Consulta métricas semanales, riesgo postural, compensación y tiempo en mala postura."),
    ]
    step_items = [
        ("01", "Crea tu perfil", "Configura tu rol, objetivo, experiencia y datos básicos."),
        ("02", "Evalúa tu postura", "Usa cuestionarios, calibración y referencias iniciales para personalizar el seguimiento."),
        ("03", "Entrena y mide", "Registra postura, compensación y estabilidad durante sesiones o rutinas."),
        ("04", "Revisa tu evolución", "Consulta tendencias, progreso semanal y señales útiles para mejorar."),
    ]
    module_items = [
        ("MO", "Monitorización", "Postura, inclinación, estabilidad y compensación en tiempo real."),
        ("CU", "Cuestionario", "Umbrales y recomendaciones según tu estado físico."),
        ("RU", "Rutinas", "Sesiones y ejercicios con métricas de ejecución."),
        ("PR", "Progreso", "Evolución semanal y tendencias posturales."),
    ]
    proof_items = [
        ("✓", "Para atletas y entrenadores", "Diseñado para entrenamiento, postura y seguimiento funcional."),
        ("✓", "Datos claros", "Información visual para tomar mejores decisiones de movimiento."),
        ("✓", "Preparado para IMU", "Compatible con evolución hacia sensores reales y datos en vivo."),
        ("✓", "MVP honesto", "Listo para incorporar testimonios y validaciones reales cuando existan."),
    ]

    def item_card(code, title, text):
        return html.Div(
            className="ax-landing-item-card",
            children=[
                html.Div(code, className="ax-landing-icon-dot"),
                html.H3(title, className="ax-landing-item-title"),
                html.P(text, className="ax-landing-item-text"),
            ],
        )

    return html.Div(
        id="axisfit-public-landing-root",
        className="surface ax-public-landing-surface",
        children=[
            html.Div(
                className="ax-public-landing",
                children=[
                    html.Section(
                        className="ax-landing-hero",
                        children=[
                            html.Div(
                                className="ax-landing-hero-card",
                                children=[
                                    html.Div("Entrena mejor · Corrige tu postura · Mide tu progreso", className="ax-landing-kicker"),
                                    html.H1("AXISFIT", className="ax-landing-brand-title"),
                                    html.H2("Monitorización postural inteligente para entrenamiento y rendimiento.", className="ax-landing-headline"),
                                    html.P(
                                        "Axisfit te ayuda a detectar compensaciones, entender tu postura y seguir tu progreso con herramientas digitales diseñadas para atletas y entrenadores.",
                                        className="ax-landing-subtitle",
                                    ),
                                    html.Div(
                                        className="ax-landing-actions",
                                        children=[
                                            dbc.Button("Empezar ahora", id="landing-register-btn", n_clicks=0, className="ax-btn ax-btn-primary"),
                                            dbc.Button("Iniciar sesión", id="landing-login-btn", n_clicks=0, className="ax-btn ax-btn-gray"),
                                        ],
                                    ),
                                    html.Div(
                                        className="ax-landing-trust-row",
                                        children=[
                                            html.Span("Dashboard clínico-deportivo", className="ax-pill"),
                                            html.Span("Postura + rutinas + progreso", className="ax-pill"),
                                            html.Span("Preparado para sensores IMU", className="ax-pill"),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="ax-landing-section-card ax-landing-mockup",
                                children=[
                                    html.Div(
                                        className="ax-landing-mockup-top",
                                        children=[
                                            html.Div("Vista previa del panel", className="ax-section-title"),
                                            html.Div("● Estable", className="ax-status-badge", style={"background": "rgba(34,197,94,.18)", "color": "#bbf7d0"}),
                                        ],
                                    ),
                                    html.Div(
                                        className="ax-landing-mockup-grid",
                                        children=[
                                            html.Div(
                                                className="ax-landing-mockup-panel",
                                                children=[
                                                    html.Div("Score postural", className="ax-label-muted mb-2"),
                                                    html.Div(className="ax-landing-gauge"),
                                                ],
                                            ),
                                            html.Div(
                                                className="ax-landing-mockup-panel",
                                                children=[
                                                    html.Div("Estado detallado", className="ax-label-muted mb-2"),
                                                    html.Div(
                                                        [
                                                            html.Span("Torácica", className="ax-label-muted"),
                                                            html.Span("Verde", className="ax-value-text"),
                                                        ],
                                                        className="ax-panel-gray-soft-row mb-2",
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.Span("Lumbar", className="ax-label-muted"),
                                                            html.Span("Verde", className="ax-value-text"),
                                                        ],
                                                        className="ax-panel-gray-soft-row",
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="ax-landing-mockup-panel",
                                        children=[
                                            html.Div(
                                                [
                                                    html.Span("Compensación", className="ax-label-muted"),
                                                    html.Span("32/100 · Baja", className="ax-value-text"),
                                                ],
                                                className="ax-panel-gray-soft-row mb-2",
                                            ),
                                            html.Div(className="ax-landing-bar", children=html.Span()),
                                        ],
                                    ),
                                    html.Div(className="ax-landing-mini-chart"),
                                ],
                            ),
                        ],
                    ),
                    html.Section(
                        className="ax-landing-section-card",
                        children=[
                            html.Div(
                                className="ax-landing-section-header",
                                children=[
                                    html.H2("Beneficios principales", className="ax-landing-section-title"),
                                    html.P(
                                        "Diseñado para entender la postura, mejorar la técnica y convertir datos en acciones claras.",
                                        className="ax-landing-section-subtitle",
                                    ),
                                ],
                            ),
                            html.Div(className="ax-landing-benefits-grid", children=[item_card(*x) for x in benefit_items]),
                        ],
                    ),
                    html.Section(
                        className="ax-landing-section-card",
                        children=[
                            html.Div(
                                className="ax-landing-section-header",
                                children=[
                                    html.H2("Cómo funciona", className="ax-landing-section-title"),
                                    html.P(
                                        "Un flujo simple para iniciar, medir y revisar evolución sin saturar al usuario.",
                                        className="ax-landing-section-subtitle",
                                    ),
                                ],
                            ),
                            html.Div(className="ax-landing-steps-grid", children=[item_card(*x) for x in step_items]),
                        ],
                    ),
                    html.Section(
                        className="ax-landing-section-card",
                        children=[
                            html.Div(
                                className="ax-landing-section-header",
                                children=[
                                    html.H2("Módulos de Axisfit", className="ax-landing-section-title"),
                                    html.P(
                                        "Acceso protegido: inicia sesión o crea una cuenta para usar las vistas internas.",
                                        className="ax-landing-section-subtitle",
                                    ),
                                ],
                            ),
                            html.Div(className="ax-landing-modules-grid", children=[item_card(*x) for x in module_items]),
                        ],
                    ),
                    html.Section(
                        className="ax-landing-section-card",
                        children=[
                            html.Div(
                                className="ax-landing-section-header",
                                children=[
                                    html.H2("Preparado para crecer con atletas y entrenadores", className="ax-landing-section-title"),
                                    html.P(
                                        "Sin cifras inventadas ni testimonios falsos: la sección queda lista para incorporar validaciones reales en próximas versiones.",
                                        className="ax-landing-section-subtitle",
                                    ),
                                ],
                            ),
                            html.Div(className="ax-landing-proof-grid", children=[item_card(*x) for x in proof_items]),
                        ],
                    ),
                    html.Section(
                        className="ax-landing-section-card ax-landing-final-cta",
                        children=[
                            html.Div(
                                children=[
                                    html.H2("Empieza a construir tu historial postural hoy.", className="ax-landing-section-title"),
                                    html.P(
                                        "Regístrate, completa tu perfil y comienza a usar Axisfit para entender mejor tu postura y tu progreso.",
                                        className="ax-landing-section-subtitle",
                                    ),
                                ]
                            ),
                            html.Div(
                                className="ax-landing-actions",
                                children=[
                                    dbc.Button("Crear cuenta", id="landing-final-register-btn", n_clicks=0, className="ax-btn ax-btn-primary"),
                                    dbc.Button("Iniciar sesión", id="landing-final-login-btn", n_clicks=0, className="ax-btn ax-btn-gray"),
                                ],
                            ),
                        ],
                    ),
                ],
            )
        ],
    )


def axisfit_footer():
    """Footer global de Axisfit, fuera del cuadro gris .surface.

    Tipografía del footer:
    - AXISFIT escala entre 20px y 25px con estilo serif tipo logotipo.
    - Contacto, Legal y Síganos en usan 10px-12px en negrita.
    - El resto del texto escala entre 10px y 12px.
    """
    return html.Footer(
        className="ax-axisfit-footer",
        children=[
            html.Div(
                className="ax-axisfit-footer-top",
                children=[
                    html.Div(
                        className="ax-axisfit-footer-brand",
                        children=[
                            html.H3("AXISFIT", className="ax-axisfit-footer-logo"),
                            html.P(
                                "Monitorización postural, rutinas y progreso para entrenamiento inteligente.",
                                className="ax-axisfit-footer-tagline",
                            ),
                            html.Div(
                                className="ax-axisfit-footer-mini-badges",
                                children=[
                                    html.Span("Postura", className="ax-axisfit-footer-mini-badge"),
                                    html.Span("Entrenamiento", className="ax-axisfit-footer-mini-badge"),
                                    html.Span("Progreso", className="ax-axisfit-footer-mini-badge"),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="ax-axisfit-footer-col",
                        children=[
                            html.Div("Contacto", className="ax-axisfit-footer-title"),
                            html.Div(
                                className="ax-axisfit-footer-contact-card",
                                children=[
                                    html.Div(
                                        className="ax-axisfit-footer-contact-list",
                                        children=[
                                            html.A("contacto@axisfit.com", href="mailto:contacto@axisfit.com", className="ax-axisfit-footer-link"),
                                            html.A("soporte@axisfit.com", href="mailto:soporte@axisfit.com", className="ax-axisfit-footer-link"),
                                            html.P("España · Atención de lunes a viernes", className="ax-axisfit-footer-text"),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="ax-axisfit-footer-col",
                        children=[
                            html.Div("Legal", className="ax-axisfit-footer-title"),
                            html.Div(
                                className="ax-axisfit-footer-two-col-grid",
                                children=[
                                    html.A("Aviso legal", href="#", className="ax-axisfit-footer-link"),
                                    html.A("Privacidad", href="#", className="ax-axisfit-footer-link"),
                                    html.A("Cookies", href="#", className="ax-axisfit-footer-link"),
                                    html.A("Términos", href="#", className="ax-axisfit-footer-link"),
                                    html.A("Descargo médico", href="#", className="ax-axisfit-footer-link"),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="ax-axisfit-footer-col ax-axisfit-footer-follow-col",
                        children=[
                            html.Div("Síganos en", className="ax-axisfit-footer-title"),
                            html.Div(
                                className="ax-axisfit-footer-follow-card",
                                children=[
                                    html.A("in", href="#", className="ax-axisfit-footer-social", title="LinkedIn"),
                                    html.A("ig", href="#", className="ax-axisfit-footer-social", title="Instagram"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="ax-axisfit-footer-bottom",
                children=[
                    html.P(
                        "Axisfit no sustituye la valoración de un profesional sanitario. La información mostrada es orientativa y debe usarse como apoyo al entrenamiento y seguimiento postural.",
                        className="ax-axisfit-footer-disclaimer",
                    ),
                    html.P("© 2026 Axisfit. Todos los derechos reservados.", className="ax-axisfit-footer-copy"),
                ],
            ),
        ],
    )


# -------- Layout general (navbar + modales + contenedor de página) --------
app.layout = html.Div([
    dcc.Store(id="session-user", storage_type="session"),
    dcc.Store(id="router", storage_type="session", data={"view": "home"}),
    dcc.Store(id="reg-base", storage_type="memory"),
    dcc.Store(id="q-reset", storage_type="memory", data=0),

    # ----- NAVBAR -----
    dbc.Navbar(
        dbc.Container(
            [
                dbc.Button(
                    html.Img(
                        src="/assets/AXISFIT.png",
                        style={
                            "height": "var(--navbar-logo-h)",
                            "width": "auto",
                            "maxWidth": "min(18vw, 220px)",
                            "borderRadius": "12px",
                            "objectFit": "contain",
                            "display": "block"
                        }
                    ),
                    id="logo-btn",
                    color="link",
                    className="p-0",
                    style={
                        "lineHeight": 0,
                        "border": "none",
                        "background": "transparent",
                        "cursor": "pointer",
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "center",
                        "height": "100%",
                        "overflow": "visible",
                        "padding": "0",
                        "margin": "0"
                    }
                ),

                html.Div(
                    [
                        dbc.Button("Monitorización", id="metrics-btn", size="md", className="btn-nav"),
                        dbc.Button("Cuestionario", id="questionnaire-btn", size="md", className="ms-2 btn-nav"),
                        dbc.Button("Rutinas", id="rutinas-btn", size="md", className="ms-2 btn-nav"),
                        dbc.Button("Progresos", id="progresos-btn", size="md", className="ms-2 btn-nav"),
                    ],
                    id="navbar-center",
                    className="d-none d-lg-flex align-items-center",
                    style={"position": "absolute", "left": "50%", "top": "50%", "transform": "translate(-50%, -50%)"}
                ),

                html.Div(
                    id="navbar-auth",
                    className="d-flex flex-row flex-nowrap align-items-center ms-auto",
                    style={"gap": "8px"}
                ),
            ],
            fluid=True,
            className="navbar-inner"
        ),
        fixed="top",
        className="shadow-sm py-0 navbar-light navbar-custom",
    ),

    # ---- MODALES (UI) -> callbacks en auth.py ----
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Iniciar sesión")),
            dbc.ModalBody(
                [
                    dbc.Input(id="login-email", placeholder="Correo electrónico", type="email", className="mb-2"),
                    dbc.Input(id="login-password", placeholder="Contraseña", type="password", className="mb-3"),
                    dbc.Alert(id="login-feedback", color="info", is_open=False)
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Cerrar", id="login-close", className="me-2", outline=True),
                    dbc.Button("Entrar", id="login-submit", color="primary",
                               style={"backgroundColor":"var(--c-accent)","border":"none"})
                ]
            ),
        ],
        id="login-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="md", fade=False
    ),

    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Crear cuenta")),
            dbc.ModalBody(
                [
                    dbc.Alert(id="reg-feedback", color="danger", is_open=False, className="mb-3"),
                    dbc.Form(
                        [
                            dbc.Label("Email", className="req"),
                            dbc.Input(id="reg-email", type="email", placeholder="tu@correo.com", className="mb-3"),
                            dbc.Label("Nombre", className="req"),
                            dbc.Input(id="reg-name", type="text", placeholder="Tu nombre completo", className="mb-3"),
                            dbc.Label("País", className="req"),
                            dcc.Dropdown(
                                id="reg-country",
                                options=[
                                    {"label": "España (ES)", "value": "ES"},
                                    {"label": "Venezuela (VE)", "value": "VE"},
                                    {"label": "México (MX)", "value": "MX"},
                                    {"label": "Argentina (AR)", "value": "AR"},
                                    {"label": "Colombia (CO)", "value": "CO"},
                                    {"label": "Chile (CL)", "value": "CL"},
                                    {"label": "Perú (PE)", "value": "PE"},
                                    {"label": "Brasil (BR)", "value": "BR"},
                                    {"label": "Estados Unidos (US)", "value": "US"},
                                    {"label": "Canadá (CA)", "value": "CA"},
                                    {"label": "Portugal (PT)", "value": "PT"},
                                    {"label": "Francia (FR)", "value": "FR"},
                                    {"label": "Italia (IT)", "value": "IT"},
                                    {"label": "Alemania (DE)", "value": "DE"},
                                    {"label": "Reino Unido (GB)", "value": "GB"},
                                ],
                                placeholder="Selecciona tu país", className="mb-3"
                            ),

                            dbc.Label("Contraseña", className="req"),
                            dbc.Input(id="reg-password", type="password",
                                      placeholder="Mín. 8, 1 mayús, 1 minús, 1 número", className="mb-2"),
                            dbc.Label("Confirmar contraseña", className="req"),
                            dbc.Input(id="reg-password2", type="password",
                                      placeholder="Repite la contraseña", className="mb-2"),
                            html.Div(
                                "La contraseña debe tener ≥8 caracteres, incluir al menos 1 mayúscula, 1 minúscula y 1 número.",
                                className="help mb-3"
                            ),

                            dbc.Label("Aceptaciones", className="req"),
                            dbc.Checklist(
                                id="reg-accepts",
                                options=[
                                    {"label": "Acepto Términos y Privacidad", "value": "terms"},
                                    {"label": "Declaro que no es dispositivo médico", "value": "disclaimer"}
                                ],
                                value=[], switch=True, className="mb-3"
                            ),

                            dbc.Label("Rol al inicio", className="req"),
                            dcc.RadioItems(
                                id="reg-role",
                                options=[
                                    {"label": "Soy Atleta", "value": "atleta"},
                                    {"label": "Soy Entrenador", "value": "entrenador"},
                                ],
                                value=None, labelStyle={"display":"block"}, className="mb-2"
                            ),
                        ]
                    )
                ]
            ),
            dbc.ModalFooter(
                [
                    html.Div(
                        dbc.Button("Usuarios registrados", id="open-users",
                                   color="secondary", outline=True, style={"width": "200px"}),
                        className="me-auto"
                    ),
                    dbc.Button("Cerrar", id="reg-close", outline=True, className="me-2"),
                    dbc.Button("Continuar", id="reg-continue", n_clicks=0, color="primary",
                               style={"backgroundColor":"var(--c-accent)","border":"none"}),
                ]
            ),
        ],
        id="reg-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="lg", fade=False
    ),

    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Perfil de Atleta")),
            dbc.ModalBody(
                [
                    dbc.Alert(id="ath-feedback", color="danger", is_open=False, className="mb-3"),
                    dbc.Form(
                        [
                            dbc.Label("Rol de uso", className="req"),
                            dcc.Dropdown(
                                id="ath-uso",
                                options=[{"label":"Gym","value":"Gym"}, {"label":"CrossFit","value":"CrossFit"}],
                                placeholder="Selecciona uso principal",
                                className="mb-3"
                            ),

                            dbc.Label("Nivel de experiencia", className="req"),
                            dcc.Dropdown(
                                id="ath-nivel",
                                options=[{"label":x, "value":x} for x in ["Novato","Intermedio","Avanzado"]],
                                placeholder="Selecciona nivel",
                                className="mb-3"
                            ),

                            dbc.Label("Frecuencia semanal", className="req"),
                            dcc.Dropdown(
                                id="ath-freq",
                                options=[{"label":x, "value":x} for x in ["1–2","3–4","5+"]],
                                placeholder="Sesiones/semana",
                                className="mb-3"
                            ),

                            dbc.Label("Molestias actuales"),
                            dcc.Dropdown(
                                id="ath-molestias",
                                options=[{"label":x,"value":x} for x in ["Cervical","Hombro","Dorsal","Lumbar","Ninguna"]],
                                placeholder="Selecciona (opcional)",
                                multi=True,
                                className="mb-3"
                            ),

                            html.Div(
                                [
                                    dbc.Label("Intensidad de dolor (VAS)", id="ath-vas-label", style={"display":"none"}),
                                    dcc.Slider(0,10,1, value=0, id="ath-dolor",
                                               tooltip={"always_visible":False}, marks=None),
                                ],
                                id="ath-vas-col",
                                style={"display":"none"},
                                className="mb-3"
                            ),

                            dbc.Label("Box/Gimnasio"),
                            dbc.Input(id="ath-box", type="text",
                                      placeholder="Nombre del Box/Gimnasio (2–50 car.)", className="mb-3"),

                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Altura (cm)"),
                                    dbc.Input(id="ath-altura", type="number",
                                              min=80, max=250, step=1, placeholder="Opcional")
                                ], md=6),
                                dbc.Col([
                                    dbc.Label("Peso (kg)"),
                                    dbc.Input(id="ath-peso", type="number",
                                              min=30, max=250, step=0.1, placeholder="Opcional")
                                ], md=6),
                            ], className="mb-2"),
                            html.Div(
                                "Nota: la intensidad (VAS) aparece si declaras molestias distintas de “Ninguna”.",
                                className="help"
                            ),
                        ]
                    )
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Atrás", id="ath-back", outline=True, className="me-2"),
                    dbc.Button("Crear cuenta", id="ath-submit", n_clicks=0, color="primary",
                               style={"backgroundColor":"var(--c-accent)","border":"none"}),
                ]
            ),
        ],
        id="athlete-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="lg", fade=False
    ),

    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Perfil de Entrenador")),
            dbc.ModalBody(
                [
                    dbc.Alert(id="coach-feedback", color="danger", is_open=False, className="mb-3"),
                    dbc.Form(
                        [
                            dbc.Label("Especialidad", className="req"),
                            dcc.Dropdown(
                                id="coach-especialidad",
                                options=[{"label":"Gym/Strength","value":"Gym/Strength"},{"label":"CrossFit","value":"CrossFit"}],
                                multi=True,
                                placeholder="Selecciona especialidades",
                                className="mb-3"
                            ),

                            dbc.Label("Años de experiencia", className="req"),
                            dcc.Dropdown(
                                id="coach-anios",
                                options=[{"label":x,"value":x} for x in ["0–1","2–4","5–9","10+"]],
                                placeholder="Selecciona rango",
                                className="mb-3"
                            ),

                            dbc.Label("Centro de trabajo"),
                            dbc.Input(id="coach-centro", type="text",
                                      placeholder="Nombre del Box/Gimnasio (2–50 car.)", className="mb-3"),

                            dbc.Label("Ubicación"),
                            dbc.Input(id="coach-ubicacion", type="text",
                                      placeholder="Ciudad / Provincia", className="mb-3"),

                            dbc.Label("Modalidad de servicio", className="req"),
                            dcc.Dropdown(
                                id="coach-modalidad",
                                options=[{"label":x,"value":x} for x in ["Presencial","Online","Híbrido"]],
                                multi=True,
                                placeholder="Selecciona modalidades",
                                className="mb-3"
                            ),

                            dbc.Label("Disponibilidad semanal", className="req"),
                            dcc.Dropdown(
                                id="coach-disponibilidad",
                                options=[{"label":x,"value":x} for x in ["Mañanas","Tardes","Mixto"]],
                                placeholder="Selecciona franja",
                                className="mb-2"
                            ),

                            dbc.Checkbox(id="coach-cred", value=False,
                                         label="Acepto verificación de credenciales (opcional)"),
                        ]
                    )
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Atrás", id="coach-back", outline=True, className="me-2"),
                    dbc.Button("Crear cuenta", id="coach-submit", n_clicks=0, color="primary",
                               style={"backgroundColor":"var(--c-accent)","border":"none"}),
                ]
            ),
        ],
        id="coach-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="lg", fade=False
    ),

    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Usuarios registrados")),
            dbc.ModalBody(html.Div(id="users-list-modal")),
            dbc.ModalFooter(dbc.Button("Cerrar", id="users-close", outline=True)),
        ],
        id="users-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="md", fade=False
    ),

    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Inicia sesión o regístrate")),
            dbc.ModalBody(
                [
                    html.P("inicia sesión o crea tu cuenta para acceder a más información.",
                           className="text-center muted"),
                    html.Div(
                        [
                            dbc.Button("Registrarse", id="access-register",
                                       style={"width": "200px"}, className="me-2"),
                            dbc.Button("Iniciar sesión", id="access-login",
                                       style={"width": "200px"}),
                        ],
                        className="d-flex justify-content-center align-items-center"
                    ),
                ]
            ),
            dbc.ModalFooter(dbc.Button("Cerrar", id="access-close", outline=True)),
        ],
        id="access-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="md", fade=False
    ),

    html.Div(className="navbar-spacer"),

    dbc.Container([html.Div(id="main-content", children=html.Div(className="surface"))], fluid=True, className="page-shell"),

    html.Div(axisfit_footer(), className="ax-footer-shell"),
])


@app.callback(
    Output("router", "data"),
    [
        Input("logo-btn", "n_clicks"),
        Input("metrics-btn", "n_clicks"),
        Input("questionnaire-btn", "n_clicks"),
        Input("rutinas-btn", "n_clicks"),
        Input("progresos-btn", "n_clicks"),
    ],
    State("session-user", "data"),
    prevent_initial_call=True
)
def update_router(n_logo, n_metrics, n_q, n_rut, n_prog, session):
    trig = dash.ctx.triggered_id

    if trig == "logo-btn":
        return {"view": "home"}

    if not (session and isinstance(session, dict) and session.get("name")):
        raise PreventUpdate

    role = (session.get("role") or "").lower()

    if trig == "metrics-btn" and (n_metrics or 0) > 0 and role == "atleta":
        return {"view": "monitor"}
    if trig == "questionnaire-btn" and (n_q or 0) > 0 and role == "atleta":
        return {"view": "questionnaire"}
    if trig == "rutinas-btn" and (n_rut or 0) > 0 and role == "atleta":
        return {"view": "routines"}
    if trig == "progresos-btn" and (n_prog or 0) > 0 and role == "atleta":
        return {"view": "progress"}

    raise PreventUpdate


@app.callback(
    Output("main-content", "children"),
    [Input("router", "data"), Input("q-reset", "data"), Input("session-user", "data")]
)
def render_main_content(router, qreset, session):
    view = (router or {}).get("view", "home")

    if view == "home":
        if session and (session.get("role") or "").lower() == "atleta":
            return athlete_home_layout()
        if session and (session.get("role") or "").lower() == "entrenador":
            return coach_home_layout()
        return axisfit_public_landing()

    if view == "monitor":
        return monitor_layout()
    if view == "questionnaire":
        return questionnaire_layout_view(reset_key=qreset)
    if view == "routines":
        return routines_layout()
    if view == "progress":
        return progress_layout()

    return html.Div(className="surface")


register_auth_callbacks(app)
register_monitor_callbacks(app)
register_questionnaire_callbacks(app)
register_coach_home_callbacks(app)
register_athlete_home_callbacks(app)

if __name__ == "__main__":
    app.run(debug=True)