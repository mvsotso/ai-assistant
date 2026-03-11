import 'package:flutter/material.dart';
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
      final tasksData = await TaskService.getTasks(limit: 5);
      if (mounted) {
        setState(() {
          _userName = user?['name'] ?? '';
          _stats = dashboard;
          _recentTasks = tasksData;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _loading = false);
    }
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Dashboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, size: 20),
            onPressed: () async {
              await AuthService.signOut();
              if (mounted) Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => const LoginScreen()));
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
                Text('Welcome, $_userName', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: AppTheme.text)),
                const SizedBox(height: 16),
                Row(children: [
                  _statCard('Total', '${_stats?['total_tasks'] ?? 0}', AppTheme.accent, Icons.list_alt),
                  const SizedBox(width: 8),
                  _statCard('Active', '${_stats?['in_progress'] ?? 0}', AppTheme.blue, Icons.play_circle_outline),
                ]),
                const SizedBox(height: 8),
                Row(children: [
                  _statCard('Overdue', '${_stats?['overdue'] ?? 0}', AppTheme.red, Icons.warning_amber),
                  const SizedBox(width: 8),
                  _statCard('Done', '${_stats?['completed'] ?? 0}', AppTheme.green, Icons.check_circle_outline),
                ]),
                const SizedBox(height: 20),
                const Text('Recent Tasks', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppTheme.text)),
                const SizedBox(height: 8),
                ..._recentTasks.map((t) => TaskCard(
                  task: t,
                  onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => TaskDetailScreen(taskId: t.id))),
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
}
