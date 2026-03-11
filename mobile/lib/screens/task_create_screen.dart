import 'package:flutter/material.dart';
import '../config/theme.dart';
import '../models/category.dart';
import '../models/task_group.dart';
import '../models/team_member.dart';
import '../models/task_template.dart';
import '../services/task_service.dart';
import '../services/category_service.dart';
import '../services/group_service.dart';
import '../services/team_service.dart';
import '../services/template_service.dart';

class TaskCreateScreen extends StatefulWidget {
  const TaskCreateScreen({super.key});
  @override
  State<TaskCreateScreen> createState() => _TaskCreateScreenState();
}

class _TaskCreateScreenState extends State<TaskCreateScreen> {
  final _titleCtrl = TextEditingController();
  final _descCtrl = TextEditingController();
  String _priority = 'medium';
  String _status = 'todo';
  DateTime? _dueDate;
  bool _saving = false;

  // Dropdown data
  List<Category> _categories = [];
  List<TaskGroup> _groups = [];
  List<TeamMember> _teamMembers = [];

  // Selected values
  String? _selectedCategory;
  String? _selectedSubcategory;
  int? _selectedGroupId;
  int? _selectedSubgroupId;
  String? _selectedAssignee;

  // Filtered lists
  List<Subcategory> _filteredSubcats = [];
  List<TaskSubGroup> _filteredSubgroups = [];

  @override
  void initState() {
    super.initState();
    _loadDropdownData();
  }

  Future<void> _loadDropdownData() async {
    try {
      final results = await Future.wait([
        CategoryService.getCategories(),
        GroupService.getGroups(),
        TeamService.getMembers(),
      ]);
      if (mounted) setState(() {
        _categories = results[0] as List<Category>;
        _groups = results[1] as List<TaskGroup>;
        _teamMembers = results[2] as List<TeamMember>;
      });
    } catch (_) {}
  }

  Future<void> _showTemplateSheet() async {
    try {
      final templates = await TemplateService.getTemplates();
      if (!mounted || templates.isEmpty) return;
      showModalBottomSheet(
        context: context,
        backgroundColor: AppTheme.surface,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
        builder: (_) => ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.all(16),
          children: [
            const Text('Choose Template',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppTheme.text)),
            const SizedBox(height: 12),
            ...templates.map((t) => ListTile(
              leading: Text(t.icon ?? '\ud83d\udccb', style: const TextStyle(fontSize: 24)),
              title: Text(t.name, style: const TextStyle(color: AppTheme.text)),
              subtitle: Text(t.titleTemplate,
                style: const TextStyle(color: AppTheme.muted, fontSize: 12)),
              trailing: Text('Used ${t.useCount}x',
                style: const TextStyle(color: AppTheme.muted, fontSize: 10)),
              onTap: () { _applyTemplate(t); Navigator.pop(context); },
            )),
          ],
        ),
      );
    } catch (_) {}
  }

  void _applyTemplate(TaskTemplate t) {
    setState(() {
      _titleCtrl.text = t.titleTemplate;
      if (t.descriptionText != null) _descCtrl.text = t.descriptionText!;
      _priority = t.priority;
      _status = t.status;
      if (t.category != null) {
        _selectedCategory = t.category;
        final cat = _categories.where((c) => c.name == t.category).firstOrNull;
        _filteredSubcats = cat?.subcategories ?? [];
      }
      if (t.subcategory != null) _selectedSubcategory = t.subcategory;
      if (t.assigneeName != null) _selectedAssignee = t.assigneeName;
      if (t.groupId != null) {
        _selectedGroupId = t.groupId;
        final grp = _groups.where((g) => g.id == t.groupId).firstOrNull;
        _filteredSubgroups = grp?.subgroups ?? [];
      }
      if (t.subgroupId != null) _selectedSubgroupId = t.subgroupId;
      if (t.dueOffsetHours != null) {
        _dueDate = DateTime.now().add(Duration(hours: t.dueOffsetHours!));
      }
    });
    TemplateService.trackUse(t.id); // fire-and-forget
  }

  Future<void> _save() async {
    if (_titleCtrl.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Title is required')));
      return;
    }
    setState(() => _saving = true);
    try {
      final body = <String, dynamic>{
        'title': _titleCtrl.text.trim(),
        'description': _descCtrl.text.trim(),
        'priority': _priority,
        'status': _status,
        if (_dueDate != null) 'due_date': _dueDate!.toIso8601String(),
        if (_selectedCategory != null) 'category': _selectedCategory,
        if (_selectedSubcategory != null) 'subcategory': _selectedSubcategory,
        if (_selectedGroupId != null) 'group_id': _selectedGroupId,
        if (_selectedSubgroupId != null) 'subgroup_id': _selectedSubgroupId,
        if (_selectedAssignee != null) 'assignee_name': _selectedAssignee,
      };
      await TaskService.createTask(body);
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed: $e')));
    }
    if (mounted) setState(() => _saving = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('New Task'),
        actions: [
          TextButton.icon(
            icon: const Icon(Icons.description_outlined, size: 16, color: AppTheme.accent),
            label: const Text('Template', style: TextStyle(fontSize: 11, color: AppTheme.accent)),
            onPressed: _showTemplateSheet,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Title
          TextField(controller: _titleCtrl,
            decoration: const InputDecoration(labelText: 'Title'),
            style: const TextStyle(color: AppTheme.text)),
          const SizedBox(height: 12),

          // Description
          TextField(controller: _descCtrl,
            decoration: const InputDecoration(labelText: 'Description'),
            maxLines: 3, style: const TextStyle(color: AppTheme.text)),
          const SizedBox(height: 12),

          // Priority
          DropdownButtonFormField<String>(
            value: _priority,
            decoration: const InputDecoration(labelText: 'Priority'),
            dropdownColor: AppTheme.card,
            items: ['low', 'medium', 'high', 'urgent'].map((p) =>
              DropdownMenuItem(value: p,
                child: Text(p.toUpperCase(), style: const TextStyle(color: AppTheme.text)))).toList(),
            onChanged: (v) => setState(() => _priority = v ?? 'medium'),
          ),
          const SizedBox(height: 12),

          // Status
          DropdownButtonFormField<String>(
            value: _status,
            decoration: const InputDecoration(labelText: 'Status'),
            dropdownColor: AppTheme.card,
            items: ['todo', 'in_progress', 'review', 'done'].map((s) =>
              DropdownMenuItem(value: s,
                child: Text(s.replaceAll('_', ' ').toUpperCase(),
                  style: const TextStyle(color: AppTheme.text)))).toList(),
            onChanged: (v) => setState(() => _status = v ?? 'todo'),
          ),
          const SizedBox(height: 12),

          // Category
          if (_categories.isNotEmpty) ...[
            DropdownButtonFormField<String>(
              value: _selectedCategory,
              decoration: const InputDecoration(labelText: 'Category'),
              dropdownColor: AppTheme.card,
              items: [
                const DropdownMenuItem<String>(value: null,
                  child: Text('None', style: TextStyle(color: AppTheme.muted))),
                ..._categories.map((c) => DropdownMenuItem<String>(
                  value: c.name,
                  child: Text('${c.icon ?? ""} ${c.name}'.trim(),
                    style: const TextStyle(color: AppTheme.text)))),
              ],
              onChanged: (v) => setState(() {
                _selectedCategory = v;
                _selectedSubcategory = null;
                final cat = _categories.where((c) => c.name == v).firstOrNull;
                _filteredSubcats = cat?.subcategories ?? [];
              }),
            ),
            const SizedBox(height: 12),
          ],

          // Subcategory
          if (_filteredSubcats.isNotEmpty) ...[
            DropdownButtonFormField<String>(
              value: _selectedSubcategory,
              decoration: const InputDecoration(labelText: 'Subcategory'),
              dropdownColor: AppTheme.card,
              items: [
                const DropdownMenuItem<String>(value: null,
                  child: Text('None', style: TextStyle(color: AppTheme.muted))),
                ..._filteredSubcats.map((s) => DropdownMenuItem<String>(
                  value: s.name,
                  child: Text(s.name, style: const TextStyle(color: AppTheme.text)))),
              ],
              onChanged: (v) => setState(() => _selectedSubcategory = v),
            ),
            const SizedBox(height: 12),
          ],

          // Group
          if (_groups.isNotEmpty) ...[
            DropdownButtonFormField<int>(
              value: _selectedGroupId,
              decoration: const InputDecoration(labelText: 'Group'),
              dropdownColor: AppTheme.card,
              items: [
                const DropdownMenuItem<int>(value: null,
                  child: Text('None', style: TextStyle(color: AppTheme.muted))),
                ..._groups.map((g) => DropdownMenuItem<int>(
                  value: g.id,
                  child: Text('${g.icon ?? ""} ${g.name}'.trim(),
                    style: const TextStyle(color: AppTheme.text)))),
              ],
              onChanged: (v) => setState(() {
                _selectedGroupId = v;
                _selectedSubgroupId = null;
                final grp = _groups.where((g) => g.id == v).firstOrNull;
                _filteredSubgroups = grp?.subgroups ?? [];
              }),
            ),
            const SizedBox(height: 12),
          ],

          // Subgroup
          if (_filteredSubgroups.isNotEmpty) ...[
            DropdownButtonFormField<int>(
              value: _selectedSubgroupId,
              decoration: const InputDecoration(labelText: 'Subgroup'),
              dropdownColor: AppTheme.card,
              items: [
                const DropdownMenuItem<int>(value: null,
                  child: Text('None', style: TextStyle(color: AppTheme.muted))),
                ..._filteredSubgroups.map((s) => DropdownMenuItem<int>(
                  value: s.id,
                  child: Text(s.name, style: const TextStyle(color: AppTheme.text)))),
              ],
              onChanged: (v) => setState(() => _selectedSubgroupId = v),
            ),
            const SizedBox(height: 12),
          ],

          // Assignee
          if (_teamMembers.isNotEmpty) ...[
            DropdownButtonFormField<String>(
              value: _selectedAssignee,
              decoration: const InputDecoration(labelText: 'Assignee'),
              dropdownColor: AppTheme.card,
              items: [
                const DropdownMenuItem<String>(value: null,
                  child: Text('Unassigned', style: TextStyle(color: AppTheme.muted))),
                ..._teamMembers.map((m) => DropdownMenuItem<String>(
                  value: m.fullName,
                  child: Text(m.fullName, style: const TextStyle(color: AppTheme.text)))),
              ],
              onChanged: (v) => setState(() => _selectedAssignee = v),
            ),
            const SizedBox(height: 12),
          ],

          // Due Date
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(
              _dueDate != null ? 'Due: ${_dueDate!.toString().split(' ').first}' : 'Set Due Date',
              style: const TextStyle(fontSize: 14, color: AppTheme.text)),
            trailing: const Icon(Icons.calendar_today, color: AppTheme.muted),
            onTap: () async {
              final date = await showDatePicker(
                context: context, initialDate: DateTime.now(),
                firstDate: DateTime.now().subtract(const Duration(days: 30)),
                lastDate: DateTime.now().add(const Duration(days: 365)),
              );
              if (date != null) setState(() => _dueDate = date);
            },
          ),
          const SizedBox(height: 24),

          // Save button
          ElevatedButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'Creating...' : 'Create Task'),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() { _titleCtrl.dispose(); _descCtrl.dispose(); super.dispose(); }
}
