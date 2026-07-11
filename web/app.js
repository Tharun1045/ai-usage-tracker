// Global Dashboard State
let currentAgent = 'all';
let currentDate = ''; // Empty string represents "Overall / All Time"
let currentTrend = '7d';
let dashboardData = null; // Stored JSON payload from API

let dailyChartInstance = null;
let hourlyChartInstance = null;
let breakdownChartInstance = null;

// Brand Colors Definition
const BRAND_COLORS = {
    codex: '#10a37f',    // OpenAI Teal
    claude: '#d97706',   // Anthropic Amber/Orange
    gemini: '#8b5cf6',   // Google Gemini Purple/Indigo
    copilot: '#2ea44f',  // GitHub Green
    cursor: '#ffffff',   // Cursor White
    groq: '#f55035',     // Groq Orange
    cline: '#ff5a00',    // Cline Orange
    roocode: '#4f46e5',  // Roo Code Indigo
    all: '#3b82f6'       // Tech Blue
};

// Utility Formatting Functions
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

function formatTokens(num) {
    if (num === undefined || num === null) {
        return "0";
    }
    if (num >= 1_000_000) {
        return `${(num / 1_000_000).toFixed(2)}M`;
    } else if (num >= 1_000) {
        return `${(num / 1_000).toFixed(1)}k`;
    }
    return num.toString();
}

function formatCost(cost) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(cost);
}

function formatDateTime(isoString) {
    if (!isoString) return "-";
    try {
        const dt = new Date(isoString);
        return dt.toLocaleString();
    } catch {
        return isoString;
    }
}

// Toast System
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.remove('hidden');
    
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4000);
}

// Liquid Tab Selector Logic
let updateLiquidTabPosition = null;

function initAgentSelector() {
    const tabs = document.querySelectorAll('.agent-tab');
    const liquidBg = document.querySelector('.selector-liquid-bg');
    
    updateLiquidTabPosition = function() {
        const activeTab = document.querySelector('.agent-tab.active');
        if (!activeTab || !liquidBg) return;
        const rect = activeTab.getBoundingClientRect();
        const parentRect = activeTab.parentElement.getBoundingClientRect();
        const left = rect.left - parentRect.left;
        liquidBg.style.transform = `translateX(${left}px)`;
        liquidBg.style.width = `${rect.width}px`;
    };
    
    // Set initial position
    setTimeout(updateLiquidTabPosition, 50);
    
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            tabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            updateLiquidTabPosition();
            
            // Trigger fetch with new filter
            currentAgent = this.dataset.agent;
            fetchStats();
        });
    });
    
    window.addEventListener('resize', updateLiquidTabPosition);
}

// Date Selector Logic
function initDateSelector() {
    const dateInput = document.getElementById('dashboard-date');
    if (!dateInput) return;
    
    dateInput.addEventListener('change', function() {
        currentDate = this.value;
        fetchStats();
    });
    
    const resetBtn = document.getElementById('reset-date-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', function() {
            currentDate = '';
            dateInput.value = '';
            fetchStats();
        });
    }
}

// Trend Timeframe Toggles Logic
function initTrendToggles() {
    const toggles = document.querySelectorAll('.trend-toggle');
    toggles.forEach(toggle => {
        toggle.addEventListener('click', function() {
            toggles.forEach(t => t.classList.remove('active'));
            this.classList.add('active');
            currentTrend = this.dataset.trend;
            renderActiveTrendChart();
        });
    });
}

// Render Comparison Badge
function updatePctBadge(elementId, value) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    if (currentAgent !== 'all' || value === undefined || value === null || value === 0) {
        el.style.display = 'none';
        return;
    }
    el.style.display = 'inline-block';
    
    const formatted = value.toFixed(1);
    if (value > 0) {
        el.textContent = `+${formatted}% vs prev`;
        el.className = 'pct-badge up';
    } else if (value < 0) {
        el.textContent = `${formatted}% vs prev`;
        el.className = 'pct-badge down';
    } else {
        el.textContent = '0% vs prev';
        el.className = 'pct-badge';
    }
}

// Render Charts Def Options
const defChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: { display: false },
        tooltip: {
            mode: 'index',
            intersect: false,
            backgroundColor: 'rgba(13, 20, 35, 0.9)',
            titleColor: '#fff',
            bodyColor: '#e5e7eb',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
            padding: 10,
            displayColors: false
        }
    },
    scales: {
        x: {
            grid: { display: false },
            ticks: {
                color: '#9ca3af',
                font: { family: 'Outfit' }
            }
        },
        y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
                color: '#9ca3af',
                font: { family: 'Outfit' },
                callback: function(value) { return formatTokens(value); }
            }
        }
    }
};

function renderActiveTrendChart() {
    if (!dashboardData) return;
    
    let chartData = [];
    let isMonthly = false;
    let titleText = "Consumption Trends";
    
    if (currentTrend === '7d') {
        chartData = dashboardData.history_7d;
        titleText = "Daily Consumption (7-Day Trend)";
    } else if (currentTrend === '30d') {
        chartData = dashboardData.history_30d;
        titleText = "Daily Consumption (30-Day Trend)";
    } else if (currentTrend === '3m') {
        chartData = dashboardData.history_3m;
        isMonthly = true;
        titleText = "Monthly Consumption (3-Month Trend)";
    } else if (currentTrend === '6m') {
        chartData = dashboardData.history_6m;
        isMonthly = true;
        titleText = "Monthly Consumption (6-Month Trend)";
    } else if (currentTrend === '1y') {
        chartData = dashboardData.history_1y;
        isMonthly = true;
        titleText = "Monthly Consumption (1-Year Trend)";
    }
    
    document.getElementById('trend-chart-title').textContent = titleText;
    renderTrendChart(chartData, isMonthly);
}

function renderTrendChart(data, isMonthly) {
    try {
        const canvas = document.getElementById('daily-chart');
        if (!canvas) return;
        
        if (typeof Chart === 'undefined') {
            canvas.parentElement.innerHTML = `<div class="loader" style="padding-top: 80px;">Chart.js could not be loaded.</div>`;
            return;
        }
        
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        
        if (dailyChartInstance) {
            dailyChartInstance.destroy();
        }
        
        let labels = [];
        if (isMonthly) {
            labels = data.map(item => {
                const parts = item.date.split('-');
                if (parts.length === 2) {
                    const date = new Date(parts[0], parts[1]-1, 1);
                    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
                }
                return item.date;
            });
        } else {
            labels = data.map(item => {
                const parts = item.date.split('-');
                if (parts.length === 3) {
                    const date = new Date(parts[0], parts[1]-1, parts[2]);
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                }
                return item.date;
            });
        }
        
        const trendChartOptions = {
            ...defChartOptions,
            scales: {
                x: { ...defChartOptions.scales.x, stacked: true },
                y: { ...defChartOptions.scales.y, stacked: true }
            },
            plugins: {
                ...defChartOptions.plugins,
                legend: {
                    display: true,
                    position: 'top',
                    align: 'end',
                    labels: {
                        color: '#9ca3af',
                        font: { family: 'Outfit', size: 10 },
                        boxWidth: 8,
                        padding: 8
                    }
                },
                tooltip: {
                    ...defChartOptions.plugins.tooltip,
                    callbacks: {
                        label: function(context) {
                            const label = context.dataset.label || '';
                            const value = context.parsed.y || 0;
                            const index = context.dataIndex;
                            const item = data[index];
                              if (item && currentAgent === 'all') {
                                  const agentsList = ['codex', 'claude', 'gemini', 'copilot', 'cursor', 'groq', 'cline', 'roocode'];
                                  const activeAgents = agentsList.filter(a => dashboardData && dashboardData.agent_breakdown && dashboardData.agent_breakdown[a] > 0);
                                  const agent = activeAgents[context.datasetIndex];
                                  const rawVal = item[`${agent}_tokens`] || 0;
                                  return `${label}: ${formatNumber(rawVal)}`;
                              } else if (item) {
                                 const rawVal = context.datasetIndex === 0 ? item.input_tokens : item.output_tokens;
                                 return `${label}: ${formatNumber(rawVal)}`;
                             }
                             return `${label}: ${formatNumber(value)}`;
                        },
                        footer: function(tooltipItems) {
                            let total = 0;
                            const index = tooltipItems[0].dataIndex;
                            const item = data[index];
                            if (item) {
                                total = item.total_tokens;
                            }
                            return `Total: ${formatNumber(total)}`;
                        }
                    }
                }
            }
        };

        let datasets = [];
        if (currentAgent === 'all') {
            const agentsList = ['codex', 'claude', 'gemini', 'copilot', 'cursor', 'groq', 'cline', 'roocode'];
            const activeAgents = agentsList.filter(a => dashboardData && dashboardData.agent_breakdown && dashboardData.agent_breakdown[a] > 0);
            
            const agentPlotted = {};
            activeAgents.forEach(a => { agentPlotted[a] = []; });
            
            for (let i = 0; i < data.length; i++) {
                const item = data[i];
                const rawVals = {};
                activeAgents.forEach(a => { rawVals[a] = item[`${a}_tokens`] || 0; });
                const total = Object.values(rawVals).reduce((sum, v) => sum + v, 0);
                
                const plottedVals = { ...rawVals };
                
                if (total > 0) {
                    const minPlotted = total * 0.04;
                    const maxAgent = Object.keys(rawVals).reduce((a, b) => rawVals[a] > rawVals[b] ? a : b);
                    
                    activeAgents.forEach(a => {
                        if (rawVals[a] > 0 && rawVals[a] < minPlotted) {
                            plottedVals[a] = minPlotted;
                        }
                    });
                    
                    const excess = Object.values(plottedVals).reduce((sum, v) => sum + v, 0) - total;
                    if (excess > 0) {
                        plottedVals[maxAgent] = Math.max(0, plottedVals[maxAgent] - excess);
                    }
                }
                
                activeAgents.forEach(a => {
                    agentPlotted[a].push(plottedVals[a]);
                });
            }
            
            const displayNames = {
                codex: 'OpenAI Codex',
                claude: 'Anthropic Claude',
                gemini: 'Google Gemini',
                copilot: 'GitHub Copilot',
                cursor: 'Cursor IDE',
                groq: 'Groq',
                cline: 'Cline',
                roocode: 'Roo Code'
            };
            
            datasets = activeAgents.map(a => ({
                label: displayNames[a],
                data: agentPlotted[a],
                backgroundColor: BRAND_COLORS[a],
                borderRadius: 4
            }));
        } else {
            // Stacked by Input/Output (with minimum height helper)
            const maxTotal = Math.max(...data.map(item => item.total_tokens || 0));
            const minOutputPlotted = maxTotal * 0.04;
            
            const inputValues = data.map(item => {
                const realInput = item.input_tokens || 0;
                const realOutput = item.output_tokens || 0;
                const total = realInput + realOutput;
                if (realOutput > 0 && realOutput < minOutputPlotted) {
                    return Math.max(0, total - minOutputPlotted);
                }
                return realInput;
            });

            const outputValues = data.map(item => {
                const realInput = item.input_tokens || 0;
                const realOutput = item.output_tokens || 0;
                const total = realInput + realOutput;
                if (realOutput > 0 && realOutput < minOutputPlotted) {
                    return Math.min(total, minOutputPlotted);
                }
                return realOutput;
            });
            
            datasets = [
                {
                    label: 'Input Tokens',
                    data: inputValues,
                    backgroundColor: '#3b82f6',
                    borderRadius: 4
                },
                {
                    label: 'Output Tokens',
                    data: outputValues,
                    backgroundColor: '#a855f7',
                    borderRadius: 4
                }
            ];
        }

        dailyChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: trendChartOptions
        });
    } catch (e) {
        console.error("Error rendering trend chart:", e);
    }
}

function renderHourlyChart(data) {
    try {
        const canvas = document.getElementById('hourly-chart');
        if (!canvas) return;
        
        if (typeof Chart === 'undefined') {
            canvas.parentElement.innerHTML = `<div class="loader" style="padding-top: 80px;">Chart.js could not be loaded.</div>`;
            return;
        }
        
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        
        if (hourlyChartInstance) {
            hourlyChartInstance.destroy();
        }
        
        const labels = data.map(item => item.hour);
        let datasets = [];
        
        const hourlyOptions = {
            ...defChartOptions,
            plugins: {
                ...defChartOptions.plugins,
                legend: {
                    display: currentAgent === 'all',
                    position: 'top',
                    align: 'end',
                    labels: {
                        color: '#9ca3af',
                        font: { family: 'Outfit', size: 9 },
                        boxWidth: 8,
                        padding: 8
                    }
                }
            }
        };
        
        if (currentAgent === 'all') {
            const agentsList = ['codex', 'claude', 'gemini', 'copilot', 'cursor', 'groq', 'cline', 'roocode'];
            const activeAgents = agentsList.filter(a => dashboardData && dashboardData.agent_breakdown && dashboardData.agent_breakdown[a] > 0);
            const displayNames = {
                codex: 'OpenAI Codex',
                claude: 'Anthropic Claude',
                gemini: 'Google Gemini',
                copilot: 'GitHub Copilot',
                cursor: 'Cursor IDE',
                groq: 'Groq',
                cline: 'Cline',
                roocode: 'Roo Code'
            };
            
            datasets = activeAgents.map(a => ({
                label: displayNames[a],
                data: data.map(item => item[`${a}_tokens`] || 0),
                borderColor: BRAND_COLORS[a],
                backgroundColor: BRAND_COLORS[a],
                borderWidth: 2,
                pointBackgroundColor: BRAND_COLORS[a],
                pointRadius: 2,
                fill: false,
                tension: 0.3
            }));
        } else {
            // Render single total line for selected agent
            const values = data.map(item => item.total_tokens);
            const gradient = ctx.createLinearGradient(0, 0, 0, 250);
            gradient.addColorStop(0, 'rgba(139, 92, 246, 0.4)');
            gradient.addColorStop(1, 'rgba(139, 92, 246, 0.0)');
            
            datasets = [{
                label: 'Usage',
                data: values,
                borderColor: '#8b5cf6',
                borderWidth: 2,
                pointBackgroundColor: '#8b5cf6',
                pointRadius: 2,
                pointHoverRadius: 5,
                fill: true,
                backgroundColor: gradient,
                tension: 0.3
            }];
        }
        
        hourlyChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: hourlyOptions
        });
    } catch (e) {
        console.error("Error rendering hourly chart:", e);
    }
}

// Render AI Provider breakdown circular chart
function renderBreakdownChart(breakdownData) {
    try {
        const canvas = document.getElementById('ai-breakdown-chart');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        
        if (breakdownChartInstance) {
            breakdownChartInstance.destroy();
        }
        
        const agentsList = ['codex', 'claude', 'gemini', 'copilot', 'cursor', 'groq', 'cline', 'roocode'];
        const displayNames = {
            codex: 'OpenAI Codex',
            claude: 'Anthropic Claude',
            gemini: 'Google Gemini',
            copilot: 'GitHub Copilot',
            cursor: 'Cursor IDE',
            groq: 'Groq',
            cline: 'Cline',
            roocode: 'Roo Code'
        };
        
        const total = agentsList.reduce((sum, a) => sum + (breakdownData[a] || 0), 0);
        if (total === 0) {
            canvas.parentElement.innerHTML = `<div class="loader" style="padding-top: 50px;">No usage logged yet.</div>`;
            return;
        }
        
        const rawVals = {};
        agentsList.forEach(a => { rawVals[a] = breakdownData[a] || 0; });
        
        const plottedVals = { ...rawVals };
        if (total > 0) {
            const minShare = total * 0.03; // 3% visual minimum share
            const maxAgent = Object.keys(rawVals).reduce((a, b) => rawVals[a] > rawVals[b] ? a : b);
            
            agentsList.forEach(a => {
                if (rawVals[a] > 0 && rawVals[a] < minShare) {
                    plottedVals[a] = minShare;
                }
            });
            
            const excess = Object.values(plottedVals).reduce((sum, v) => sum + v, 0) - total;
            if (excess > 0) {
                plottedVals[maxAgent] = Math.max(0, plottedVals[maxAgent] - excess);
            }
        }
        
        const activeLabels = [];
        const activeData = [];
        const activeRaw = [];
        const activeColors = [];
        
        agentsList.forEach(a => {
            if (rawVals[a] > 0) {
                activeLabels.push(displayNames[a]);
                activeData.push(plottedVals[a]);
                activeRaw.push(rawVals[a]);
                activeColors.push(BRAND_COLORS[a]);
            }
        });

        breakdownChartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: activeLabels,
                datasets: [{
                    data: activeData,
                    backgroundColor: activeColors,
                    borderWidth: 1,
                    borderColor: 'rgba(255, 255, 255, 0.1)'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            color: '#9ca3af',
                            font: { family: 'Outfit', size: 10 },
                            boxWidth: 8,
                            padding: 8
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(13, 20, 35, 0.9)',
                        titleColor: '#fff',
                        bodyColor: '#e5e7eb',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        callbacks: {
                            label: function(context) {
                                const index = context.dataIndex;
                                const rawVal = activeRaw[index];
                                const pct = ((rawVal / total) * 100).toFixed(2);
                                return `${context.label}: ${formatTokens(rawVal)} (${pct}%)`;
                            }
                        }
                    }
                },
                cutout: '65%'
            }
        });
    } catch (e) {
        console.error("Error rendering breakdown chart:", e);
    }
}

// Fetch and Populate Dashboard Data
async function fetchStats() {
    try {
        const response = await fetch(`/api/stats?agent=${currentAgent}&date=${currentDate}`);
        const data = await response.json();
        
        if (data.error) {
            showToast(`Error: ${data.error}`, 'error');
            return;
        }
        
        // Save globally
        dashboardData = data;
        
        // Dynamic Tab Visibility
        const tabsEl = document.querySelectorAll('.agent-tab');
        tabsEl.forEach(tab => {
            const agent = tab.dataset.agent;
            if (agent && agent !== 'all') {
                const tokenCount = data.agent_breakdown[agent] || 0;
                if (tokenCount > 0) {
                    tab.classList.remove('hidden-tab');
                } else {
                    tab.classList.add('hidden-tab');
                }
            }
        });
        
        // Re-align active sliding liquid indicator after layout shift
        if (typeof updateLiquidTabPosition === 'function') {
            setTimeout(updateLiquidTabPosition, 50);
        }
        
        // 0. Update Calendar Limits and Selection
        const dateInput = document.getElementById('dashboard-date');
        if (dateInput) {
            dateInput.min = data.config.min_date;
            dateInput.max = data.config.max_date;
            dateInput.value = data.config.selected_date; 
        }
        
        const isAllTime = data.config.is_all_time;
        document.getElementById('selected-date-label').textContent = data.timeframes.selected_date.label;
        
        // Update metric title card & group titles based on filter type
        document.getElementById('focus-date-title').textContent = isAllTime ? "Overall Summary" : "Selected Day Summary";
        document.querySelector('.project-panel .panel-header h3').textContent = isAllTime ? "Top Projects (All Time)" : "Top Projects (Selected Day)";
        document.querySelector('.model-panel .panel-header h3').textContent = isAllTime ? "Models (All Time)" : "Models (Selected Day)";
        document.querySelector('.sessions-section .panel-header h3').textContent = isAllTime ? "Chat Sessions (All Time)" : "Chat Sessions (Selected Day)";
        
        // 1. Update Metrics Cards with percentages (if All AIs is selected)
        document.getElementById('summary-total-tokens').textContent = formatNumber(data.summary.total_tokens);
        document.getElementById('summary-total-cost').textContent = formatCost(data.summary.estimated_cost);
        document.getElementById('summary-in-tokens').textContent = formatTokens(data.summary.input_tokens);
        document.getElementById('summary-out-tokens').textContent = formatTokens(data.summary.output_tokens);
        
        document.getElementById('today-total-tokens').textContent = formatNumber(data.timeframes.selected_date.total);
        document.getElementById('today-cost').textContent = formatCost(data.timeframes.selected_date.cost);
        document.getElementById('today-in-tokens').textContent = formatTokens(data.timeframes.selected_date.input);
        document.getElementById('today-out-tokens').textContent = formatTokens(data.timeframes.selected_date.output);
        
        document.getElementById('5h-total-tokens').textContent = formatNumber(data.timeframes.last_5h.total);
        document.getElementById('5h-cost').textContent = formatCost(data.timeframes.last_5h.cost);
        document.getElementById('5h-in-tokens').textContent = formatTokens(data.timeframes.last_5h.input);
        document.getElementById('5h-out-tokens').textContent = formatTokens(data.timeframes.last_5h.output);
        
        document.getElementById('7d-total-tokens').textContent = formatNumber(data.timeframes.last_7d.total);
        document.getElementById('7d-cost').textContent = formatCost(data.timeframes.last_7d.cost);
        document.getElementById('7d-in-tokens').textContent = formatTokens(data.timeframes.last_7d.input);
        document.getElementById('7d-out-tokens').textContent = formatTokens(data.timeframes.last_7d.output);
        
        // Bind comparison percentage badges
        updatePctBadge('today-pct', data.timeframes.today.pct_change);
        updatePctBadge('5h-pct', data.timeframes.last_5h.pct_change);
        updatePctBadge('7d-pct', data.timeframes.last_7d.pct_change);
        
        // 2. Render Charts
        renderActiveTrendChart();
        renderHourlyChart(data.history_24h);
        
        // Toggle breakdown panel visibility and grid layouts dynamically
        const breakdownPanel = document.getElementById('breakdown-panel');
        const detailsGrid = document.querySelector('.details-grid');
        
        if (currentAgent === 'all') {
            if (breakdownPanel) breakdownPanel.style.display = 'flex';
            if (detailsGrid) {
                detailsGrid.classList.add('all-agent');
                detailsGrid.classList.remove('single-agent');
                detailsGrid.style.gridTemplateColumns = '';
            }
            renderBreakdownChart(data.agent_breakdown);
        } else {
            if (breakdownPanel) breakdownPanel.style.display = 'none';
            if (detailsGrid) {
                detailsGrid.classList.add('single-agent');
                detailsGrid.classList.remove('all-agent');
                detailsGrid.style.gridTemplateColumns = '';
            }
        }
        
        // 3. Populate Projects List (with premium brand badges and inline SVGs)
        const projectsList = document.getElementById('projects-list');
        if (data.projects.length === 0) {
            projectsList.innerHTML = `<div class="loader">No project logs found.</div>`;
        } else {
            const maxTokens = Math.max(...data.projects.map(p => p.total_tokens));
            projectsList.innerHTML = data.projects.map(proj => {
                const pct = maxTokens > 0 ? (proj.total_tokens / maxTokens) * 100 : 0;
                
                let baseName = proj.project_name;
                let providerBadge = '';
                
                const endings = {
                    '(Codex)': { class: 'codex', label: 'Codex', svg: `<path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z"/></svg> Codex</span>` },
                    '(Claude)': { class: 'claude', label: 'Claude', svg: `<path d="M17.3041 3.541h-3.6718l6.696 16.918H24Zm-10.6082 0L0 20.459h3.7442l1.3693-3.5527h7.0052l1.3693 3.5528h3.7442L10.5363 3.5409Zm-.3712 10.2232 2.2914-5.9456 2.2914 5.9456Z"/>` },
                    '(Gemini)': { class: 'gemini', label: 'Gemini', svg: `<path d="M12 2c0 4.97-4.03 9-9 9 4.97 0 9 4.03 9 9 0-4.97 4.03-9 9-9-4.97 0-9-4.03-9-9zm5 5c0 2.49-2.01 4.5-4.5 4.5 2.49 0 4.5 2.01 4.5 4.5 0-2.49 2.01-4.5 4.5-4.5-2.49 0-4.5-2.01-4.5-4.5z"/>` },
                    '(Copilot)': { class: 'copilot', label: 'Copilot', svg: `<path d="M12 2a10 10 0 0 0-7.38 16.74c.48.45.69 1.15.53 1.78l-.34 1.34a.5.5 0 0 0 .61.61l1.34-.34a2 2 0 0 1 1.78.53A10 10 0 1 0 12 2zm1 13h-2v-2h2zm0-4h-2V7h2z"/>` },
                    '(Cursor)': { class: 'cursor', label: 'Cursor', svg: `<path d="M13.64 21.97c-.38.03-.64-.26-.64-.64V12.7L21.32 16c.38.16.48.51.26.83l-6.9 4.97c-.32.22-.7.22-1.04.17zM10.87 2v10.7L2.55 9.38c-.38-.16-.48-.51-.26-.83l6.9-4.97c.32-.22.7-.22 1.04-.17a.64.64 0 0 1 .64.59z"/>` },
                    '(Groq)': { class: 'groq', label: 'Groq', svg: `<path d="M13 2L3 14h9l-1 8 10-12h-9z"/>` },
                    '(Cline)': { class: 'cline', label: 'Cline', svg: `<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>`, stroke: true },
                    '(Roo Code)': { class: 'roocode', label: 'Roo Code', svg: `<path d="M16 18l6-6-6-6M8 6l-6 6 6 6M12 4l-4 16"/>`, stroke: true }
                };
                
                let foundEnding = null;
                for (const suffix of Object.keys(endings)) {
                    if (proj.project_name.endsWith(suffix)) {
                        foundEnding = suffix;
                        break;
                    }
                }
                
                if (foundEnding) {
                    baseName = proj.project_name.replace(` ${foundEnding}`, '');
                    const cfg = endings[foundEnding];
                    const fillStrokeAttr = cfg.stroke ? `fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"` : `fill="currentColor"`;
                    providerBadge = `<span class="badge-mini ${cfg.class}"><svg viewBox="0 0 24 24" class="badge-logo-svg" ${fillStrokeAttr}>${cfg.svg}</svg> ${cfg.label}</span>`;
                }
                
                return `
                    <div class="rank-item">
                        <div class="rank-info">
                            <span class="rank-name">${baseName} ${providerBadge}</span>
                            <span class="rank-value">${formatNumber(proj.total_tokens)} tokens (${formatCost(proj.estimated_cost)})</span>
                        </div>
                        <div class="rank-bar-bg">
                            <div class="rank-bar-fill" style="width: ${pct}%"></div>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        // 4. Populate Models List Table
        const modelsList = document.getElementById('models-list');
        if (data.models.length === 0) {
            modelsList.innerHTML = `<tr><td colspan="4" class="table-loader">No model usage logged.</td></tr>`;
        } else {
            modelsList.innerHTML = data.models.map(m => `
                <tr>
                    <td><strong>${m.model}</strong></td>
                    <td>${formatNumber(m.total_tokens)}</td>
                    <td>${formatNumber(m.cached_input_tokens)}</td>
                    <td><strong style="color: #34d399">${formatCost(m.estimated_cost)}</strong></td>
                </tr>
            `).join('');
        }
        
        // 5. Populate Sessions List Table
        const sessionsList = document.getElementById('sessions-list');
        if (data.sessions.length === 0) {
            sessionsList.innerHTML = `<tr><td colspan="6" class="table-loader">No active sessions found.</td></tr>`;
        } else {
            sessionsList.innerHTML = data.sessions.map(s => {
                const shortSess = s.session_id ? s.session_id.substring(0, 8) + '...' : 'unknown';
                return `
                    <tr>
                        <td><span class="session-badge" title="${s.session_id || ''}">${shortSess}</span></td>
                        <td>${s.project_name}</td>
                        <td>${formatNumber(s.total_tokens)}</td>
                        <td>${formatNumber(s.reasoning_tokens)}</td>
                        <td>${formatDateTime(s.last_active)}</td>
                        <td><strong style="color: #34d399">${formatCost(s.estimated_cost)}</strong></td>
                    </tr>
                `;
            }).join('');
        }
        
        // Re-trigger Lucide Icons compilation
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
        
    } catch (e) {
        showToast(`Failed to fetch stats: ${e.message}`, 'error');
    }
}

// Bind Actions
document.getElementById('scan-btn').addEventListener('click', async function() {
    const btn = this;
    btn.disabled = true;
    btn.classList.add('btn-loading');
    const originalText = btn.innerHTML;
    btn.innerHTML = `<i data-lucide="refresh-cw" class="btn-icon"></i> Scanning Logs...`;
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    try {
        const response = await fetch('/api/scan');
        const data = await response.json();
        
        if (data.status === 'success') {
            const res = data.results;
            showToast(`Scan complete! ${res.new} new, ${res.updated} updated, ${res.skipped} skipped. Added ${res.events_added} events.`);
            await fetchStats();
        } else {
            showToast(`Scan failed: ${data.message}`, 'error');
        }
    } catch (e) {
        showToast(`Request failed: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.classList.remove('btn-loading');
        btn.innerHTML = originalText;
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }
});

// Initial Load
window.addEventListener('DOMContentLoaded', () => {
    initAgentSelector();
    initDateSelector();
    initTrendToggles();
    fetchStats();
});
