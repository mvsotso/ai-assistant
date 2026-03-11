import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../config/theme.dart';
import '../services/task_service.dart';
import '../services/auth_service.dart';
import '../widgets/task_card.dart';
import '../models/task.dart';
import 'task_detail_screen.dart';
import 'login_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});
  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Map<String, dynamic>? _stats;
  List<Task> _recentTasks = [];
  bool _loading = true;
  String _userName = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final user = await AuthService.getUser();
      final dashboard = await TaskService.getDashboard();
      // Use recent_tasks from dashboard response, fallback to separate call
      List<Task> recent = [];
      if (dashboard['recent_tasks'] != null) {
        recent = (dashboard['recent_tasks'] as List)
            .map((t) => Task.fromJson(t))
            .take(5)
            .toList();
      } else {
        recent = await TaskService.getTasks(limit: 5);
      }
      if (mounted) {
        setState(() {
          _userName = user?['name'] ?? '';
          _stats = dashboard;
          _recentTasks = recent;
          _loading = false;
        });
      }
    } catch (e) {
      debugPrint('Dashboard load error: $e');
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Read a stat value from nested 'stats' or top-level
  dynamic _s(String key) {
    return _stats?['stats']?[key] ?? _stats?[key] ?? 0;
  }

  Widget _statCard(String label, String value, Color color, IconData icon) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppTheme.card, borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppTheme.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(icon, size: 16, color: color),
              const SizedBox(width: 6),
              Text(label, style: const TextStyle(fontSize: 11, color: AppTheme.muted)),
            ]),
            const SizedBox(height: 8),
            Text(value, style: TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: color)),
          ],
        ),
      ),
    );
  }

  Widget _kpiCard(String label, String value, IconData icon, Color color, {String? trend}) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppTheme.card, borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppTheme.border),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 4),
            Expanded(child: Text(label, style: const TextStyle(fontSize: 10, color: AppTheme.muted),
              overflow: TextOverflow.ellipsis)),
          ]),
          const SizedBox(height: 6),
          Row(children: [
            Text(value, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: color)),
            if (trend != null) ...[
              const SizedBox(width: 4),
              Text(trend, style: TextStyle(fontSize: 10,
                color: trend.startsWith('+') ? AppTheme.green : AppTheme.red)),
            ],
          ]),
        ]),
      ),
    );
  }

  Widget _statusPieChart() {
    final s = _stats?['stats'];
    if (s == null) return const SizedBox.shrink();
    final todo = (s['todo'] ?? 0).toDouble();
    final active = (s['in_progress'] ?? 0).toDouble();
    final review = (s['review'] ?? 0).toDouble();
    final done = (s['done'] ?? 0).toDouble();
    if (todo + active + review + done == 0) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.card, borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Status Distribution',
          style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppTheme.text)),
        const SizedBox(height: 12),
        SizedBox(
          height: 160,
          child: PieChart(PieChartData(
            sections: [
              if (todo > 0) PieChartSectionData(value: todo, title: 'To Do',
                color: const Color(0xFF6B7094), radius: 45,
                titleStyle: const TextStyle(fontSize: 9, color: Colors.white, fontWeight: FontWeight.w600)),
              if (active > 0) PieChartSectionData(value: active, title: 'Active',
                color: AppTheme.blue, radius: 45,
                titleStyle: const TextStyle(fontSize: 9, color: Colors.white, fontWeight: FontWeight.w600)),
              if (review > 0) PieChartSectionData(value: review, title: 'Review',
                color: AppTheme.purple, radius: 45,
                titleStyle: const TextStyle(fontSize: 9, color: Colors.white, fontWeight: FontWeight.w600)),
              if (done > 0) PieChartSectionData(value: done, title: 'Done',
                color: AppTheme.green, radius: 45,
                titleStyle: const TextStyle(fontSize: 9, color: Colors.white, fontWeight: FontWeight.w600)),
            ],
            centerSpaceRadius: 28,
            sectionsSpace: 2,
          )),
        ),
      ]),
    );
  }

  Widget _trendChart() {
    final trend = _stats?['completion_trend'] as List?;
    if (trend == null || trend.isEmpty) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.card, borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Completion Trend',
          style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppTheme.text)),
        const SizedBox(height: 12),
        SizedBox(
          height: 160,
          child: LineChart(LineChartData(
            gridData: const FlGridData(show: false),
            titlesData: const FlTitlesData(
              leftTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
              rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
              topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
              bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
            ),
            borderData: FlBorderData(show: false),
            lineBarsData: [
              LineChartBarData(
                spots: trend.asMap().entries.map((e) =>
                  FlSpot(e.key.toDouble(), (e.value['count'] ?? 0).toDouble())).toList(),
                isCurved: true,
                color: AppTheme.accent,
                barWidth: 2,
                dotData: const FlDotData(show: true),
                belowBarData: BarAreaData(show: true,
                  color: AppTheme.accent.withOpacity(0.1)),
              ),
            ],
          )),
        ),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final kpis = _stats?['kpis'];
    final prev = _stats?['previous_period'];
    return Scaffold(
      appBar: AppBar(
        title: const Text('Dashboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, size: 20),
            onPressed: () async {
              await AuthService.signOut();
              if (mounted) Navigator.pushReplacement(context,
                MaterialPageRoute(builder: (_) => const LoginScreen()));
            },
          ),
        ],
      ),
      body: _loading
        ? const Center(child: CircularProgressIndicator())
        : RefreshIndicator(
            onRefresh: _load,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text('Welcome, $_userName',
                  style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: AppTheme.text)),
                const SizedBox(height: 16),

                // Basic stat cards
                Row(children: [
                  _statCard('Total', '${_stats?['stats']?['total_tasks'] ?? _stats?['total_tasks'] ?? 0}',
                    AppTheme.accent, Icons.list_alt),
                  const SizedBox(width: 8),
                  _statCard('Active', '${_stats?['stats']?['in_progress'] ?? _stats?['in_progress'] ?? 0}',
                    AppTheme.blue, Icons.play_circle_outline),
                ]),
                const SizedBox(height: 8),
                Row(children: [
                  _statCard('Overdue', '${_stats?['stats']?['overdue'] ?? _stats?['overdue'] ?? 0}',
                    AppTheme.red, Icons.warning_amber),
                  const SizedBox(width: 8),
                  _statCard('Done', '${_stats?['stats']?['done'] ?? _stats?['completed'] ?? _stats?['done'] ?? 0}',
                    AppTheme.green, Icons.check_circle_outline),
                ]),

                // KPI cards
                if (kpis != null) ...[
                  const SizedBox(height: 16),
                  const Text('Key Performance',
                    style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppTheme.text)),
                  const SizedBox(height: 8),
                  Row(children: [
                    _kpiCard('Avg Days', '${(kpis['avg_completion_days'] ?? 0).toStringAsFixed(1)}',
                      Icons.speed, AppTheme.accent,
                      trend: prev != null ? _calcTrend(kpis['avg_completion_days'], prev['avg_days'], invert: true) : null),
                    const SizedBox(width: 8),
                    _kpiCard('On-Time', '${kpis['on_time_pct'] ?? 0}%',
                      Icons.timer, AppTheme.green,
                      trend: prev != null ? _calcTrend(kpis['on_time_pct'], prev['on_time_pct']) : null),
                  ]),
                  const SizedBox(height: 8),
                  Row(children: [
                    _kpiCard('Overdue', '${kpis['overdue_count'] ?? 0}',
                      Icons.warning_amber, AppTheme.red,
                      trend: prev != null ? _calcTrend(kpis['overdue_count'], prev['overdue'], invert: true) : null),
                    const SizedBox(width: 8),
                    _kpiCard('This Week', '${kpis['tasks_this_week'] ?? 0}',
                      Icons.calendar_today, AppTheme.blue),
                  ]),
                ],

                // Charts
                const SizedBox(height: 16),
                _statusPieChart(),
                const SizedBox(height: 12),
                _trendChart(),

                // Recent tasks
                const SizedBox(height: 20),
                const Text('Recent Tasks',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppTheme.text)),
                const SizedBox(height: 8),
                ..._recentTasks.map((t) => TaskCard(
                  task: t,
                  onTap: () => Navigator.push(context,
                    MaterialPageRoute(builder: (_) => TaskDetailScreen(taskId: t.id))),
                )),
                if (_recentTasks.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(32),
                    child: Center(child: Text('No tasks yet', style: TextStyle(color: AppTheme.muted))),
                  ),
              ],
            ),
          ),
    );
  }

  String? _calcTrend(dynamic current, dynamic previous, {bool invert = false}) {
    if (current == null || previous == null) return null;
    final c = (current is num ? current : 0).toDouble();
    final p = (previous is num ? previous : 0).toDouble();
    if (p == 0) return null;
    final diff = c - p;
    if (diff == 0) return null;
    final isPositive = invert ? diff < 0 : diff > 0;
    return '${isPositive ? "+" : ""}${diff.toStringAsFixed(0)}';
  }
}
