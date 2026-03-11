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
  bool _searching = false;
  String _searchQuery = '';
  final _searchCtrl = TextEditingController();

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

  List<Task> get _displayTasks {
    if (!_searching || _searchQuery.isEmpty) return _tasks;
    final q = _searchQuery.toLowerCase();
    return _tasks.where((t) =>
      t.title.toLowerCase().contains(q) ||
      (t.description?.toLowerCase().contains(q) ?? false) ||
      (t.category?.toLowerCase().contains(q) ?? false) ||
      (t.assignee?.toLowerCase().contains(q) ?? false)
    ).toList();
  }

  @override
  Widget build(BuildContext context) {
    final display = _displayTasks;
    return Scaffold(
      appBar: AppBar(
        title: _searching
          ? TextField(
              controller: _searchCtrl,
              autofocus: true,
              decoration: const InputDecoration(
                hintText: 'Search tasks...',
                border: InputBorder.none,
                hintStyle: TextStyle(color: AppTheme.muted),
              ),
              style: const TextStyle(color: AppTheme.text, fontSize: 16),
              onChanged: (q) => setState(() => _searchQuery = q),
            )
          : const Text('Tasks'),
        actions: [
          IconButton(
            icon: Icon(_searching ? Icons.close : Icons.search, size: 20),
            onPressed: () => setState(() {
              _searching = !_searching;
              if (!_searching) { _searchCtrl.clear(); _searchQuery = ''; }
            }),
          ),
        ],
      ),
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
                  child: display.isEmpty
                    ? Center(child: Text(
                        _searching ? 'No matching tasks' : 'No tasks found',
                        style: const TextStyle(color: AppTheme.muted)))
                    : ListView.builder(
                        itemCount: display.length,
                        itemBuilder: (_, i) => TaskCard(
                          task: display[i],
                          onTap: () async {
                            await Navigator.push(context,
                              MaterialPageRoute(builder: (_) => TaskDetailScreen(taskId: display[i].id)));
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
          await Navigator.push(context,
            MaterialPageRoute(builder: (_) => const TaskCreateScreen()));
          _load();
        },
        backgroundColor: AppTheme.accent,
        child: const Icon(Icons.add),
      ),
    );
  }

  @override
  void dispose() { _searchCtrl.dispose(); super.dispose(); }
}
