import 'package:flutter/material.dart';
import '../config/theme.dart';
import '../models/task.dart';
import '../services/task_service.dart';
import '../widgets/task_card.dart';
import 'task_detail_screen.dart';
import 'task_create_screen.dart';

class TaskListScreen extends StatefulWidget {
  const TaskListScreen({super.key});
  @override
  State<TaskListScreen> createState() => _TaskListScreenState();
}

class _TaskListScreenState extends State<TaskListScreen> {
  List<Task> _tasks = [];
  bool _loading = true;
  String? _statusFilter;

  final _statuses = [null, 'todo', 'in_progress', 'review', 'done'];
  final _labels = ['All', 'To Do', 'In Progress', 'Review', 'Done'];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final tasks = await TaskService.getTasks(status: _statusFilter, limit: 100);
      if (mounted) setState(() { _tasks = tasks; _loading = false; });
    } catch (e) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Tasks')),
      body: Column(
        children: [
          // Status filter chips
          SizedBox(
            height: 44,
            child: ListView.separated(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              scrollDirection: Axis.horizontal,
              itemCount: _statuses.length,
              separatorBuilder: (_, __) => const SizedBox(width: 6),
              itemBuilder: (_, i) => ChoiceChip(
                label: Text(_labels[i], style: const TextStyle(fontSize: 12)),
                selected: _statusFilter == _statuses[i],
                selectedColor: AppTheme.accent.withOpacity(0.2),
                onSelected: (_) { setState(() => _statusFilter = _statuses[i]); _load(); },
              ),
            ),
          ),
          Expanded(
            child: _loading
              ? const Center(child: CircularProgressIndicator())
              : RefreshIndicator(
                  onRefresh: _load,
                  child: _tasks.isEmpty
                    ? const Center(child: Text('No tasks found', style: TextStyle(color: AppTheme.muted)))
                    : ListView.builder(
                        itemCount: _tasks.length,
                        itemBuilder: (_, i) => TaskCard(
                          task: _tasks[i],
                          onTap: () async {
                            await Navigator.push(context, MaterialPageRoute(builder: (_) => TaskDetailScreen(taskId: _tasks[i].id)));
                            _load();
                          },
                        ),
                      ),
                ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          await Navigator.push(context, MaterialPageRoute(builder: (_) => const TaskCreateScreen()));
          _load();
        },
        backgroundColor: AppTheme.accent,
        child: const Icon(Icons.add),
      ),
    );
  }
}
