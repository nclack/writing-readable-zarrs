#!/usr/bin/env python3
import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import statistics
import subprocess


DEFAULT_WORKTREE = Path('/mnt/main0/home/nclack/tmp/2026-09-07-chucky-microscopy-pr/worktree')
DEFAULT_MAIN = Path('/mnt/main0/home/nclack/src/chucky')
POLICY = 'coverage-qualified-through-final-close-v2'
STANDARD_PATHS = [
    'build-microscopy-study-20260913/pilot-3667862/study.json',
    'build-microscopy-study-20260913/discovery-3667908/study.json',
    'build-microscopy-next-experiment-20260913/run-3671242/study.json',
    'build-microscopy-fs-pareto-20260914/run-3689339/study.json',
    'build-microscopy-final-20260916/run-3702747/discard/study.json',
    'build-microscopy-final-20260916/run-3702747/transfer/study.json',
    'build-microscopy-confirmation-3rounds-20260916/run-3704091/confirmation/study.json',
    'build-microscopy-confirmation-3rounds-20260916/run-3704091/refinement/study.json',
    'build-microscopy-cpu-scaling-20260916/turin-3708156/study.json',
    'build-microscopy-cpu-scaling-20260916/turin-3708278/study.json',
    'build-microscopy-cpu-scaling-20260916/l40-3708541/study.json',
    'build-microscopy-unified-20260916/turin-3710801/study.json',
    'build-microscopy-unified-corrected-20260916/turin-3710982/core/study.json',
    'build-microscopy-unified-corrected-20260916/turin-3710982/transfer/study.json',
]
CONTROL_PATHS = [
    'build-microscopy-output-pool-20260913/run-3671630/study.json',
    'build-microscopy-cosem-v2-20260914/run-3681071/study.json',
]


def read_json(path):
    return json.loads(path.read_text())


def stable(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(stable(value).encode()).hexdigest()


def number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def product(values):
    return math.prod(values) if values and all(isinstance(v, int) and v > 0 for v in values) else None


def flag(command, name):
    try:
        return command[command.index(name) + 1]
    except (ValueError, IndexError):
        return None


def storage_record(document, source):
    storage = document.get('storage')
    locator = str(source) + '#/storage' if storage else None
    if not storage:
        for name in ('filesystem.log', 'filesystem.stdout', 'mount.stdout', 'storage-private.json'):
            candidate = source.parent / name
            if candidate.exists():
                try:
                    storage = read_json(candidate)
                    locator = str(candidate)
                    break
                except (ValueError, OSError):
                    pass
    if not storage and (source.parent / 'filesystem.txt').exists():
        locator = str(source.parent / 'filesystem.txt')
        content = Path(locator).read_text()
        storage = {'fstype': 'nfs' if ' nfs ' in content else None, 'options': None}
    storage = storage or {}
    if 'filesystems' in storage:
        item = next((x for x in storage['filesystems'] if x.get('fstype') == 'nfs'),
                    next(iter(storage['filesystems']), {}))
    else:
        item = storage
    options = item.get('options')
    if isinstance(options, str):
        parsed = dict((x.split('=', 1) + [True])[:2] for x in options.split(','))
    else:
        parsed = options or {}
    return {'record': storage, 'source_locator': locator,
            'fstype': item.get('fstype'), 'options': options,
            'nconnect': number(parsed.get('nconnect')), 'target': item.get('target'),
            'export': item.get('source'), 'export_identity_sha256': storage.get('export_identity_sha256')}


def study_metadata(document, path, kind, report_selection):
    build = document.get('build', document.get('image_benchmark', document.get('machine', {}).get('build', {})))
    if not isinstance(build, dict):
        build = {'description': build}
    plan = document.get('plan', {})
    machine = document.get('machine', {})
    if not machine and (path.parent / 'environment.json').exists():
        environment = read_json(path.parent / 'environment.json')
        machine = {'hostname': environment.get('SLURM_JOB_NODELIST'),
                   'cpu_count': number(environment.get('SLURM_CPUS_PER_TASK')),
                   'environment': environment}
    identity = document.get('id') or ('microscopy-calibration-3666599' if kind == 'calibration' else path.stem)
    status = document.get('status', 'complete' if kind in ('calibration', 'regular_sweep') else None)
    disposition = 'historical'
    if any(s[0] == identity for s in report_selection):
        disposition = 'partially_selected_in_current_report'
    if 'workers-' in identity:
        disposition = 'historical_worker_comparison_with_withdrawn_repeated_plane_cases'
    if identity.endswith('3710801'):
        disposition = 'cancelled;checkpoint_status_running'
    if status == 'failed':
        disposition = 'failed_partial_study'
    corpus = document.get('corpus', {})
    return {'id': identity, 'kind': kind, 'status': status, 'disposition': disposition,
            'created': document.get('created', document.get('started', machine.get('date'))),
            'finished': document.get('finished'), 'machine': machine, 'build': build,
            'native_build': document.get('native_build', document.get('build_origin')),
            'corpus': {k: v for k, v in corpus.items() if k != 'resolved_pack_paths'},
            'plan': plan, 'plan_sha256': document.get('plan_sha256'),
            'storage': storage_record(document, path), 'sink_options': document.get('sink_options'),
            'allocation': document.get('allocation'), 'source_file': str(path),
            'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'image_protocol': document.get('image_protocol'),
            'source_aliases': [], 'report_selection': [list(x) for x in sorted(report_selection) if x[0] == identity],
            'observations': len(document.get('records', document.get('runs', [])))}


def record_signature(document):
    return digest([{'id': r.get('id'), 'case_id': r.get('case_id'), 'role': r.get('role'),
                    'started': r.get('started'),
                    'result': {k: v for k, v in r.get('result', {}).items()
                               if k not in ('command', 'fs_root')}} for r in document.get('records', [])])


def identical_alias(meta, path):
    if path.exists() and str(path) != meta['source_file']:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum != meta['source_sha256']:
            raise ValueError('Expected duplicate differs: ' + str(path))
        meta['source_aliases'].append({'path': str(path), 'sha256': checksum, 'identical_full_file': True,
                                      'measurement_content_matches': True})


def build_settings(meta, config):
    build = meta['build']
    settings = build.get('build_settings', {})
    return (number(config.get('io_workers', settings.get('CHUCKY_IO_WORKERS'))),
            number(config.get('buffers', settings.get('CHUCKY_OUTPUT_BUFFERS'))))


def attach_layout_policy(meta, repo):
    build = meta['build']
    native = meta.get('native_build') or {}
    revision = build.get('compiled_revision', native.get('compiled_revision')) or build.get('revision', build.get('source_revision', meta['machine'].get('commit')))
    policy = {'revision': revision, 'source_file': None, 'source_sha256': None,
              'minimum_raw_shard_capacity_bytes': None, 'maximum_raw_shard_capacity_bytes': None,
              'default_concurrent_shard_target': None}
    if revision:
        for name in ('bench/bench_stream_microscopy.c', 'bench/bench_stream_images.c'):
            result = subprocess.run(['git', 'show', revision + ':' + name], cwd=repo, capture_output=True, text=True)
            if result.returncode:
                continue
            policy['source_file'] = name
            policy['source_sha256'] = hashlib.sha256(result.stdout.encode()).hexdigest()
            for field, output in [('min_shard_bytes', 'minimum_raw_shard_capacity_bytes'),
                                  ('max_shard_bytes', 'maximum_raw_shard_capacity_bytes')]:
                match = re.search(r'\.' + field + r'\s*=\s*(\d+)(?:ull|u|ll)?\s*<<\s*(\d+)', result.stdout)
                if match:
                    policy[output] = int(match[1]) << int(match[2])
            match = re.search(r'\.target_concurrent_shards\s*=\s*(\d+)', result.stdout)
            if match:
                policy['default_concurrent_shard_target'] = int(match[1])
            break
    meta['native_layout_policy'] = policy


def validity(result, profile):
    reasons = []
    window = result.get('measurement', {})
    if result.get('status') != 'pass':
        reasons.append('status_not_pass')
    if window.get('policy') != POLICY:
        reasons.append('measurement_policy_missing_or_different')
    if window.get('coverage_status') != 'sufficient':
        reasons.append('coverage_not_sufficient')
    for key, limit in [('warmup_complete_batches', 2), ('complete_batches', 4), ('generation_transitions', 2)]:
        if not isinstance(window.get(key), int) or window[key] < limit:
            reasons.append(key + '_below_required')
    elapsed = window.get('elapsed_s')
    if elapsed is None or elapsed <= 0:
        reasons.append('missing_elapsed')
    else:
        drain = window.get('drain_s')
        append = window.get('append_s')
        if drain is None or drain > 0.1 * elapsed + 1e-6:
            reasons.append('excessive_or_missing_drain')
        if append is None or append < max(0.25, profile.get('duration_s', profile.get('duration', 0))) - 1e-5:
            reasons.append('insufficient_append_duration')
        if not isinstance(window.get('warmup_s'), (int, float)) or window['warmup_s'] < max(0.25, profile.get('warmup_s', profile.get('warmup', 0))) - 1e-5:
            reasons.append('insufficient_warmup')
    logical = result.get('logical_input_bytes', window.get('logical_input_bytes'))
    minimum = profile.get('min_gib')
    if minimum is not None and (logical is None or logical < math.ceil(minimum * 2**30)):
        reasons.append('minimum_logical_work_not_reached')
    if not isinstance(logical, int) or logical <= 0 or not isinstance(window.get('output_bytes'), int) or window['output_bytes'] <= 0:
        reasons.append('missing_logical_or_output_bytes')
    return reasons


def make_row(meta, record, result, config, pointer, order, report_selection, role=None):
    window = result.get('measurement', {})
    replay = result.get('image_replay', {})
    image = result.get('image_input', {})
    input_record = record.get('input', meta['plan'].get('input', {}))
    if not image and isinstance(input_record, dict):
        image = input_record.get('provenance', input_record)
    dtype = result.get('dtype', config.get('dtype', replay.get('dtype')))
    bpe = {'u8': 1, 'u16': 2, 'u16le': 2, 'f32': 4, 'f32le': 4}.get(dtype)
    input_id = result.get('input_id', config.get('input_id', image.get('input_id', input_record.get('id'))))
    backend = result.get('backend', config.get('backend', replay.get('backend')))
    sink = result.get('sink', config.get('sink'))
    chunk = replay.get('chunk_shape')
    shape = replay.get('shape')
    reference = replay.get('reference_shape')
    cps = replay.get('chunks_per_shard')
    dimensions = window.get('geometry', {}).get('dimensions', [])
    if not chunk and dimensions:
        chunk = [d['chunk_size'] for d in dimensions]
        reference = [d['reference_size'] for d in dimensions]
        cps = [d['chunks_per_shard'] for d in dimensions]
    shard = [a * b for a, b in zip(chunk, cps)] if chunk and cps else None
    chunk_bytes = bpe * product(chunk) if bpe and product(chunk) else result.get('chunk_bytes', config.get('chunk_bytes'))
    source_bytes = replay.get('source_bytes')
    planes = len(image['plane_order']) if image.get('plane_order') else None
    if planes is None and shape and source_bytes and bpe:
        frame_bytes = math.prod(shape[1:]) * bpe
        if frame_bytes and source_bytes % frame_bytes == 0:
            planes = source_bytes // frame_bytes
    source_hash = image.get('pack_sha256', image.get('sha256', input_record.get('sha256')))
    profile = record.get('profile', record.get('settings', {}))
    if not isinstance(profile, dict):
        profile = record.get('settings', {})
    codec = result.get('codec', config.get('codec', replay.get('codec')))
    role = role or record.get('role', 'sample')
    record_id = record.get('id', f'record-{order:04d}')
    command = result.get('command', record.get('command', []))
    io_workers, buffers = build_settings(meta, config)
    storage = meta['storage']
    data_issue = 'repeated_source_plane_within_chunk' if planes and chunk and chunk[0] > planes else None
    reasons = validity(result, profile)
    selection_reasons = []
    planned_microscopy = config.get('scenario') == 'microscopy' or config.get('fill') == 'images'
    content = 'microscopy' if replay or planned_microscopy else 'synthetic_or_low_level_control'
    scope_source = 'recorded_image_replay' if replay else ('retained_case_configuration' if planned_microscopy else 'control_configuration')
    if content != 'microscopy':
        selection_reasons.append('not_microscopy')
    if data_issue:
        selection_reasons.append(data_issue)
    if meta['kind'] in ('calibration', 'output_control'):
        selection_reasons.append('timing_or_fixed_layout_control')
    if meta['status'] != 'complete':
        selection_reasons.append('incomplete_study')
    if role != 'sample':
        selection_reasons.append('reference_or_control')
    if reasons:
        selection_reasons.extend(reasons)
    logical = result.get('logical_input_bytes', window.get('logical_input_bytes'))
    output = window.get('output_bytes', result.get('output_bytes'))
    warmup = window.get('warmup_input_bytes')
    padded_source = replay.get('source_padded_bytes', window.get('source_bytes'))
    spatial_frame = (math.ceil(shape[1] / chunk[1]) * chunk[1] * math.ceil(shape[2] / chunk[2]) * chunk[2] * bpe
                     if shape and chunk and len(shape) == 3 and bpe else None)
    start_plane = ((warmup // spatial_frame) % planes if isinstance(warmup, int) and spatial_frame and planes else None)
    extent_frames = shape[0] if shape else None
    remainder_planes = extent_frames % planes if extent_frames and planes else None
    active = math.prod(math.ceil(n / d) for n, d in zip(reference[1:], shard[1:])) if reference and shard else None
    measured_s = window.get('elapsed_s')
    throughput = result.get('throughput_logical_gibs')
    if throughput is None and logical and measured_s:
        throughput = logical / 2**30 / measured_s
    requested_block = result.get('blosc_block_bytes', config.get('blosc_block_bytes'))
    if codec and not codec.startswith('blosc-'):
        requested_block = None
    target = number(flag(command, '--concurrent-shards'))
    target_source = 'recorded_command' if target is not None else None
    if target is None:
        target = number(config.get('shards'))
        target_source = 'recorded_control_configuration' if target is not None else None
    layout_policy = meta.get('native_layout_policy', {})
    if target is None and replay:
        target = layout_policy.get('default_concurrent_shard_target')
        target_source = 'archived_source_default' if target is not None else None
    build = meta['build']
    native = meta.get('native_build') or {}
    machine = meta['machine']
    row = {
        'row_id': meta['id'] + '/' + record_id, 'source_file': meta['source_file'],
        'source_record': pointer, 'study_id': meta['id'], 'study_kind': meta['kind'],
        'study_status': meta['status'], 'archive_disposition': meta['disposition'],
        'run_id': record_id, 'configuration_id': record.get('case_id', record.get('case', result.get('id'))),
        'record_order': order, 'role': role, 'round': record.get('round'), 'repeat': record.get('repeat'),
        'batch_id': record.get('batch_id'), 'started': record.get('started'),
        'status': result.get('status'), 'error': result.get('error', record.get('error')),
        'recorded_attempt': window.get('attempt'), 'max_attempts': window.get('max_attempts'),
        'earlier_native_attempt_details_retained': False if window.get('attempt', 1) > 1 else None,
        'discarded_attempts_s': window.get('discarded_attempts_s'),
        'original_measurement_valid': not reasons, 'validity_exclusions': ';'.join(reasons),
        'frontier_candidate_record': not selection_reasons, 'frontier_exclusions': ';'.join(selection_reasons),
        'current_report_selected': (meta['id'], input_id, backend) in report_selection,
        'content': content, 'workload_scope_source': scope_source, 'data_issue': data_issue, 'tool': 'Chucky',
        'runner_revision': build.get('revision', build.get('source_revision', machine.get('commit'))),
        'compiled_revision': build.get('compiled_revision', native.get('compiled_revision')),
        'binary_sha256': build.get('executable_sha256'),
        'machine': machine.get('name', machine.get('hostname')),
        'hostname': machine.get('hostname'), 'allocated_cpus': machine.get('cpu_count'),
        'gpu': machine.get('gpu'), 'backend': backend,
        'worker_threads': result.get('worker_threads', config.get('max_threads')),
        'requested_workers': config.get('max_threads'), 'io_workers': io_workers, 'output_buffers': buffers,
        'memory_budget_bytes': window.get('geometry', {}).get('memory_budget_bytes'),
        'sink': sink, 'destination': result.get('fs_root', flag(command, '-o')),
        'storage_type': storage['fstype'] if sink == 'fs' else ('discard' if sink == 'discard' else None),
        'nconnect': storage['nconnect'] if sink == 'fs' else None,
        'mount_record': storage['source_locator'] if sink == 'fs' else None,
        'mount_options': storage['options'] if sink == 'fs' else None,
        'workload': 'raw_pack_cyclic_streaming_replay' if content == 'microscopy' else 'synthetic_or_low_level_control',
        'source_format': 'raw_predecoded_planes' if content == 'microscopy' else None,
        'source_io_timed': False if replay else None, 'source_decoding_timed': False if replay else None,
        'source_staging': 'whole_raw_pack_preloaded_and_zero_padded_before_timing' if replay else None,
        'input_id': input_id, 'dataset_version': image.get('dataset_version', input_record.get('dataset_version')),
        'input_sha256': source_hash, 'corpus_revision': meta['corpus'].get('revision'),
        'manifest_sha256': image.get('manifest_sha256', meta['corpus'].get('manifest_sha256')),
        'dtype': dtype, 'array_shape': shape, 'reference_shape': reference, 'chunk_shape': chunk,
        'raw_chunk_bytes': chunk_bytes, 'chunks_per_shard': cps, 'shard_shape': shard,
        'raw_shard_capacity_bytes': bpe * product(shard) if bpe and product(shard) else None,
        'shard_capacity_basis': 'uncompressed_full_geometry' if shard else None,
        'minimum_raw_shard_capacity_bytes': layout_policy.get('minimum_raw_shard_capacity_bytes') if replay else None,
        'maximum_raw_shard_capacity_bytes': layout_policy.get('maximum_raw_shard_capacity_bytes') if replay else None,
        'shard_capacity_bounds_source': 'native_layout_policy_in_study_metadata' if replay and layout_policy.get('source_file') else None,
        'concurrent_shard_target': target, 'concurrent_shard_target_source': target_source,
        'actual_layer_shards_geometry': active,
        'simultaneously_active_io_files_measured': None,
        'codec': codec, 'codec_level': replay.get('codec_level', config.get('level', result.get('level'))),
        'codec_level_is_hint': replay.get('codec_level_is_hint'),
        'shuffle': replay.get('shuffle', result.get('blosc_shuffle', config.get('blosc_shuffle'))),
        'blosc_block_requested_bytes': requested_block, 'blosc_block_effective_measured_bytes': None,
        'gpu_block_model_bytes': min(requested_block, chunk_bytes) if backend == 'gpu' and requested_block and chunk_bytes else None,
        'source_planes': planes, 'source_raw_bytes': source_bytes, 'source_padded_bytes': padded_source,
        'source_start_plane_after_warmup': start_plane, 'logical_frames': extent_frames,
        'full_source_cycles': extent_frames // planes if extent_frames and planes else None,
        'source_cycle_tail_planes': remainder_planes,
        'logical_input_bytes': logical, 'submitted_bytes': result.get('submitted_bytes', window.get('input_bytes')),
        'padded_chunk_bytes': result.get('padded_input_bytes'),
        'measured_sink_write_bytes': output, 'output_scope': window.get('output_scope'),
        'final_stored_bytes': None, 'metadata_bytes_stored': None, 'index_bytes_stored': None,
        'logical_payload_bytes': result.get('shard_padding', {}).get('logical_payload_bytes'),
        'internal_padding_bytes': result.get('shard_padding', {}).get('internal_padding_bytes'),
        'd2h_payload_bytes': result.get('d2h_transfer', {}).get('payload_bytes_transferred'),
        'd2h_metadata_bytes': result.get('d2h_transfer', {}).get('metadata_bytes_transferred'),
        'reported_logical_fold': result.get('logical_compression_fold'),
        'reported_padded_fold': result.get('compression_fold'),
        'throughput_logical_gibs': throughput,
        'logical_rate_derived_from_byte_counters': result.get('throughput_logical_gibs') is None and throughput is not None,
        'throughput_submitted_gibs': result.get('throughput_in_gibs'),
        'throughput_sink_write_gibs': result.get('throughput_out_gibs'),
        'timing_policy': window.get('policy'), 'measurement_s': measured_s,
        'requested_duration_s': window.get('requested_duration_s', profile.get('duration_s', profile.get('duration'))),
        'minimum_logical_gib': profile.get('min_gib'), 'append_s': window.get('append_s'),
        'drain_s': window.get('drain_s'), 'drain_fraction': window.get('drain_fraction'),
        'process_wall_s': result.get('process_wall_s', record.get('process_wall_s', record.get('execution_wall_s'))),
        'requested_warmup_s': window.get('requested_warmup_s'), 'warmup_s': window.get('warmup_s'),
        'warmup_input_bytes': warmup, 'warmup_output_bytes': window.get('warmup_output_bytes'),
        'warmup_drain_s': window.get('warmup_drain_s'), 'prep_s': window.get('prep_s'),
        'source_load_s': replay.get('load_s'), 'stream_init_s': result.get('init_s'),
        'context_init_s': replay.get('context_init_s'), 'coverage_status': window.get('coverage_status'),
        'warmup_complete_batches': window.get('warmup_complete_batches'),
        'complete_batches': window.get('complete_batches'), 'generation_transitions': window.get('generation_transitions'),
        'append_bytes': window.get('append_bytes'), 'target_batch_bytes': replay.get('target_batch_bytes'),
        'actual_batch_bytes': replay.get('actual_batch_bytes'), 'epochs_per_batch': replay.get('epochs_per_batch'),
        'arrival_bytes_per_s': number(record.get('environment', {}).get('CHUCKY_BENCH_ARRIVAL_BYTES_PER_S')),
        'completion_pause_ms': number(record.get('environment', {}).get('CHUCKY_BENCH_COMPLETION_PAUSE_MS')),
        'host_peak_rss_bytes': result.get('memory_host_peak_bytes'),
        'host_baseline_rss_bytes': result.get('memory_host_baseline_bytes'),
        'host_memory_reading_failed': result.get('memory_host_reading_failed'),
        'device_free_memory_delta_bytes': result.get('memory_device_used_bytes'),
        'memory_estimate_bytes': result.get('memory_estimate_total_bytes'),
        'pinned_memory_estimate_bytes': result.get('memory_estimate_pinned_bytes'),
        'memory_measured_bytes_legacy': result.get('memory_measured_bytes'),
        'command': command, 'profile': profile, 'control_config': config if meta['kind'] == 'output_control' else None,
    }
    group_fields = ['study_id', 'input_id', 'input_sha256', 'dataset_version', 'dtype', 'backend', 'worker_threads',
                    'hostname', 'allocated_cpus', 'sink', 'storage_type', 'nconnect', 'timing_policy',
                    'requested_duration_s', 'requested_warmup_s', 'minimum_logical_gib', 'io_workers', 'output_buffers',
                    'memory_budget_bytes', 'arrival_bytes_per_s', 'completion_pause_ms', 'data_issue']
    group = {key: row[key] for key in group_fields}
    group['logical_spatial_shape'] = shape[1:] if shape else None
    group['source_order'] = replay.get('order')
    group['chunk_depth'] = chunk[0] if chunk else None
    row['comparison_group'] = digest(group)[:20]
    row['comparison_group_definition'] = group
    return row


def collect(worktree, main):
    index = read_json(worktree / 'bench/studies/microscopy/index.json')
    report_selection = {(source['study'], item['input'], backend)
                        for item in index['report'] for source in item['sources'] for backend in source['backends']}
    rows, metadata, signatures = [], {}, {}
    for relative in STANDARD_PATHS:
        path = worktree / relative
        document = read_json(path)
        meta = study_metadata(document, path, 'retained_study', report_selection)
        attach_layout_policy(meta, worktree)
        metadata[meta['id']] = meta
        signatures[meta['id']] = record_signature(document)
        for order, record in enumerate(document['records'], 1):
            config = document['plan']['cases'][record['case_id']]
            rows.append(make_row(meta, record, record['result'], config, f'#/records/{order-1}', order, report_selection))
    alias_paths = [worktree / 'bench/studies/microscopy' / entry['path'] for entry in index['studies']]
    main_index = read_json(main / 'bench/studies/microscopy/index.json')
    alias_paths.extend(main / 'bench/studies/microscopy' / entry['path'] for entry in main_index['studies'])
    for name in ('2026-09-13-microscopy-study-pilot-3667862', '2026-09-13-microscopy-discovery-3667908'):
        alias_paths.append(worktree.parents[1] / name / 'study.json')
    for path in alias_paths:
        if not path.exists():
            continue
        document = read_json(path)
        identity = document.get('id')
        if identity not in metadata:
            raise ValueError('Unmapped indexed study: ' + str(path))
        matches = record_signature(document) == signatures[identity]
        if not matches:
            raise ValueError('Copies disagree on retained observations: ' + str(path))
        metadata[identity]['source_aliases'].append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                                   'measurement_content_matches': matches})
    path = worktree / 'build-microscopy-calibration-20260913/calibration.json'
    document = read_json(path)
    meta = study_metadata(document, path, 'calibration', report_selection)
    attach_layout_policy(meta, worktree)
    identical_alias(meta, worktree.parents[1] / '2026-09-13-microscopy-calibration-3666599/calibration.json')
    metadata[meta['id']] = meta
    for order, record in enumerate(document['records'], 1):
        config = document['plan']['cases'][record['case']]
        adapted = dict(record, id=f'record-{order:04d}', case_id=record['case'], profile=record['settings'])
        result = record['run']
        rows.append(make_row(meta, adapted, result, config, f'#/records/{order-1}', order, report_selection,
                             'calibration_' + str(record.get('profile', 'unknown'))))
    runtime_root = worktree.parents[1] / '2026-09-13-microscopy-runtime'
    for section in ('calibration', 'cpu-control-repeat'):
        path = runtime_root / section / 'executions.jsonl'
        source_meta = read_json(path.parent / 'metadata.json')
        plan = source_meta.get('plan', {})
        document = {'id': 'microscopy-runtime-' + section + '-' + str(source_meta['job_id']),
                    'status': 'complete', 'created': source_meta.get('started_utc'),
                    'finished': source_meta.get('finished_utc'),
                    'machine': {'hostname': source_meta.get('host'), 'name': source_meta.get('host'),
                                'cpu_count': len(source_meta['affinity']['allowed']),
                                'cpu_affinity': source_meta['affinity']['selected'],
                                'commit': source_meta.get('source_commit', plan.get('source_commit'))},
                    'build': source_meta.get('build', {'revision': source_meta.get('source_commit')}),
                    'corpus': read_json(path.parent / 'verified-corpus.json'), 'plan': plan}
        meta = study_metadata(document, path, 'calibration', report_selection)
        attach_layout_policy(meta, worktree)
        meta['runtime_metadata'] = {k: v for k, v in source_meta.items() if k not in ('plan', 'corpus', 'build')}
        metadata[meta['id']] = meta
        cases = {c['id']: c['spec'] for c in plan.get('cases', [])}
        with path.open() as stream:
            for i, line in enumerate(stream):
                raw = json.loads(line)
                case_id = raw.get('case', source_meta.get('case', {}).get('id'))
                config = cases.get(case_id, source_meta.get('case', {}).get('spec', {}))
                record = {'id': f'line-{i+1:04d}', 'case_id': case_id, 'round': raw.get('pair'),
                          'profile': {'warmup_s': source_meta.get('warmup_s', plan.get('warmup_s')),
                                      'duration_s': source_meta.get('duration_s', plan.get('duration_s')),
                                      'min_gib': raw['minimum_gib']}}
                row = make_row(meta, record, raw['result'], config, f'line:{i+1}', i+1, report_selection, 'runtime_calibration')
                row['calibration_trial'] = raw.get('trial')
                rows.append(row)
                meta['observations'] = i + 1
    path = main / 'bench/results/reef-l40-432380c-20260912-microscopy-256k.json'
    document = read_json(path)
    meta = study_metadata(document, path, 'regular_sweep', report_selection)
    attach_layout_policy(meta, worktree)
    identical_alias(meta, worktree / 'bench/results' / path.name)
    identical_alias(meta, main.parent / 'chucky-startup/bench/results' / path.name)
    metadata[meta['id']] = meta
    for i, run in enumerate(document['runs']):
        executions = run.get('repetitions', {}).get('executions')
        if not executions:
            raise ValueError('Summary-only regular sweep row requires a separate adapter')
        for j, result in enumerate(executions):
            config = {k: run.get(k) for k in ('backend', 'codec', 'dtype', 'sink', 'input_id', 'level', 'blosc_shuffle', 'blosc_block_bytes')}
            enriched = dict(result)
            for key in ('image_input', 'input_id', 'backend', 'codec', 'dtype', 'sink', 'chunk_bytes', 'image_asset_id', 'id'):
                if key not in enriched and key in run:
                    enriched[key] = run[key]
            record = {'id': f'run-{i+1:03d}-repeat-{j+1}', 'case_id': run['id'], 'repeat': j+1,
                      'profile': {'warmup_s': document['measurement_policy']['warmup_s'],
                                  'duration_s': document['measurement_policy']['duration_s'],
                                  'min_gib': document['image_protocol']['minimum_bytes'] / 2**30}}
            rows.append(make_row(meta, record, enriched, config, f'#/runs/{i}/repetitions/executions/{j}',
                                 len(rows)+1, report_selection))
    for relative in CONTROL_PATHS:
        path = worktree / relative
        document = read_json(path)
        meta = study_metadata(document, path, 'output_control', report_selection)
        attach_layout_policy(meta, worktree)
        metadata[meta['id']] = meta
        for section in ('records', 'references', 'recovery'):
            for i, record in enumerate(document[section]):
                adapted = dict(record)
                adapted.setdefault('id', f'{section}-{i+1:04d}')
                adapted.setdefault('case_id', record.get('config', {}).get('backend', 'io-reference') + '-' + str(i+1) if section == 'references' else adapted['id'])
                fixed = document['plan']['fixed']
                adapted['profile'] = {'warmup_s': fixed['warmup_s'], 'duration_s': fixed['duration_s'],
                                      'min_gib': fixed['minimum_logical_bytes'] / 2**30}
                config = dict(fixed, **record.get('config', {}))
                config.setdefault('input_id', document['plan']['input']['id'])
                config.setdefault('dtype', document['plan']['input']['dtype'])
                row = make_row(meta, adapted, record['result'], config, f'#/{section}/{i}', i+1,
                               report_selection, 'sample' if section == 'records' else section)
                trace = record.get('trace') or {}
                for key in ('mean_queued_payload_mib', 'peak_queued_payload_mib', 'mean_active_writes', 'idle_worker_fraction',
                            'pool_full_fraction', 'buffer_lifetime_p95_ms', 'write_completion_p95_ms', 'arrival_rate_bytes_s'):
                    row['control_' + key] = trace.get(key)
                if 'throughput_gibs' in record['result']:
                    row['control_io_throughput_gibs'] = record['result']['throughput_gibs']
                    row['control_io_measured_bytes'] = record['result'].get('measured_bytes')
                rows.append(row)
    totals = Counter(r['study_id'] for r in rows)
    for identity, meta in metadata.items():
        meta['exported_observations'] = totals[identity]
    return rows, metadata, index


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: stable(v) if isinstance(v, (list, dict, bool)) else v for k, v in row.items()})
    return {key: sorted({type(row[key]).__name__ for row in rows if row.get(key) is not None}) for key in fields}


def read_csv(path, schema):
    rows = []
    with path.open(newline='') as stream:
        for raw in csv.DictReader(stream):
            row = {}
            for key, value in raw.items():
                types = schema.get(key, [])
                row[key] = None if value == '' else (json.loads(value) if 'str' not in types else value)
            rows.append(row)
    return rows


def summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['comparison_group'], row['configuration_id'], row['role'])].append(row)
    summaries = []
    for (group, config, role), records in sorted(grouped.items(), key=lambda item: str(item[0])):
        first = records[0]
        valid = [r for r in records if r['original_measurement_valid'] and r.get('throughput_logical_gibs') is not None]
        rates = [r['throughput_logical_gibs'] for r in valid]
        logical = sum(r['logical_input_bytes'] for r in valid)
        output = sum(r['measured_sink_write_bytes'] for r in valid)
        fields = ['study_id', 'study_kind', 'archive_disposition', 'study_status', 'input_id', 'dataset_version',
                  'input_sha256', 'machine', 'hostname', 'backend', 'allocated_cpus', 'worker_threads',
                  'sink', 'storage_type', 'nconnect', 'codec', 'codec_level', 'shuffle', 'dtype',
                  'chunk_shape', 'raw_chunk_bytes', 'shard_shape', 'raw_shard_capacity_bytes',
                  'concurrent_shard_target', 'actual_layer_shards_geometry', 'blosc_block_requested_bytes',
                  'gpu_block_model_bytes', 'io_workers', 'output_buffers', 'requested_duration_s',
                  'requested_warmup_s', 'minimum_logical_gib', 'current_report_selected', 'data_issue',
                  'comparison_group_definition', 'source_file']
        summary = {k: first.get(k) for k in fields}
        summary.update(summary_id=digest([group, config, role])[:20], comparison_group=group,
                       configuration_id=config, role=role, attempts=len(records), valid_observations=len(valid),
                       failure_records=sum(r['status'] != 'pass' for r in records),
                       excluded_records=sum(not r['frontier_candidate_record'] for r in records),
                       run_ids=[r['row_id'] for r in records],
                       median_logical_gibs=statistics.median(rates) if rates else None,
                       min_logical_gibs=min(rates) if rates else None, max_logical_gibs=max(rates) if rates else None,
                       logical_byte_sum=logical if valid else None, sink_write_byte_sum=output if valid else None,
                       summed_logical_fold=logical / output if output else None,
                       sink_write_bytes_per_logical_byte=output / logical if logical else None,
                       sink_write_bytes_per_logical_gib=output / logical * 2**30 if logical else None,
                       minimum_measurement_s=min((r['measurement_s'] for r in valid), default=None),
                       maximum_measurement_s=max((r['measurement_s'] for r in valid), default=None),
                       median_drain_fraction=statistics.median([r['drain_fraction'] for r in valid if r['drain_fraction'] is not None]) if any(r['drain_fraction'] is not None for r in valid) else None,
                       minimum_logical_bytes=min((r['logical_input_bytes'] for r in valid), default=None),
                       maximum_logical_bytes=max((r['logical_input_bytes'] for r in valid), default=None),
                       cycles_have_partial_tails=any(r['source_cycle_tail_planes'] for r in valid),
                       proxy_frontier_eligible=bool(valid) and all(r['frontier_candidate_record'] for r in records),
                       strict_final_stored_size_winner=None,
                       proxy_frontier=None, proxy_within_10pct=None, proxy_10pct_winner=None,
                       proxy_size_penalty_percent=None, size_basis='measured_shard_write_bytes_per_logical_byte')
        summaries.append(summary)
    by_group = defaultdict(list)
    for row in summaries:
        if row['proxy_frontier_eligible']:
            by_group[row['comparison_group']].append(row)
    for group in by_group.values():
        sizes = {r['summary_id']: Fraction(r['sink_write_byte_sum'], r['logical_byte_sum']) for r in group}
        smallest = min(sizes.values())
        eligible = [r for r in group if sizes[r['summary_id']] <= smallest * Fraction(11, 10)]
        best = max(r['median_logical_gibs'] for r in eligible)
        for row in group:
            size = sizes[row['summary_id']]
            row['proxy_size_penalty_percent'] = float((size / smallest - 1) * 100)
            row['proxy_within_10pct'] = size <= smallest * Fraction(11, 10)
            row['proxy_10pct_winner'] = row['proxy_within_10pct'] and row['median_logical_gibs'] == best
            row['proxy_frontier'] = not any(
                sizes[other['summary_id']] <= size and other['median_logical_gibs'] >= row['median_logical_gibs']
                and (sizes[other['summary_id']] < size or other['median_logical_gibs'] > row['median_logical_gibs'])
                for other in group)
            row['tested_configurations_in_group'] = len(group)
            row['tested_chunk_bytes_in_group'] = sorted({r['raw_chunk_bytes'] for r in group})
    return summaries


def comparisons(summaries, rows):
    by_group = defaultdict(list)
    for row in summaries:
        if row['proxy_frontier_eligible']:
            by_group[row['comparison_group']].append(row)
    winners = []
    for group in by_group.values():
        for winner in (r for r in group if r['proxy_10pct_winner']):
            rivals = [r for r in group if r['proxy_within_10pct'] and r['summary_id'] != winner['summary_id']
                      and max(r['min_logical_gibs'], winner['min_logical_gibs']) <= min(r['max_logical_gibs'], winner['max_logical_gibs'])]
            smaller = [r for r in group if r['raw_chunk_bytes'] < winner['raw_chunk_bytes'] and r['proxy_within_10pct']]
            larger = [r for r in group if r['raw_chunk_bytes'] > winner['raw_chunk_bytes'] and r['proxy_within_10pct']]
            record = dict(winner)
            record['overlapping_eligible_rivals'] = [r['summary_id'] for r in rivals]
            record['best_smaller_eligible_summary_id'] = max(smaller, key=lambda r: r['median_logical_gibs'])['summary_id'] if smaller else None
            record['best_larger_eligible_summary_id'] = max(larger, key=lambda r: r['median_logical_gibs'])['summary_id'] if larger else None
            record['supported_raw_chunk_range_16_to_64k'] = 16384 <= winner['raw_chunk_bytes'] <= 65536
            winners.append(record)
    blocks = defaultdict(list)
    by_id = {r['row_id']: r for r in rows}
    for row in summaries:
        if row['proxy_frontier_eligible'] and row.get('blosc_block_requested_bytes'):
            key = [row['comparison_group'], row['codec'], row['codec_level'], row['shuffle'], row['chunk_shape'], row['shard_shape']]
            blocks[stable(key)].append(row)
    block_rows = []
    for group in blocks.values():
        for a, b in itertools.combinations(sorted(group, key=lambda r: r['blosc_block_requested_bytes']), 2):
            if a['blosc_block_requested_bytes'] == b['blosc_block_requested_bytes']:
                continue
            a_rounds = {by_id[r]['round']: by_id[r]['throughput_logical_gibs'] for r in a['run_ids'] if by_id[r]['round'] is not None}
            b_rounds = {by_id[r]['round']: by_id[r]['throughput_logical_gibs'] for r in b['run_ids'] if by_id[r]['round'] is not None}
            pairs = [b_rounds[r] / a_rounds[r] for r in sorted(a_rounds.keys() & b_rounds.keys())]
            block_rows.append({'study_id': a['study_id'], 'comparison_group': a['comparison_group'],
                               'input_id': a['input_id'], 'backend': a['backend'], 'sink': a['sink'],
                               'codec': a['codec'], 'codec_level': a['codec_level'], 'shuffle': a['shuffle'],
                               'chunk_shape': a['chunk_shape'], 'raw_chunk_bytes': a['raw_chunk_bytes'],
                               'smaller_block_request_bytes': a['blosc_block_requested_bytes'],
                               'larger_block_request_bytes': b['blosc_block_requested_bytes'],
                               'smaller_request_summary_id': a['summary_id'], 'larger_request_summary_id': b['summary_id'],
                               'larger_request_median_gibs': b['median_logical_gibs'], 'smaller_request_median_gibs': a['median_logical_gibs'],
                               'larger_vs_smaller_median_ratio': b['median_logical_gibs'] / a['median_logical_gibs'],
                               'matched_rounds': len(pairs), 'matched_round_ratio_median': statistics.median(pairs) if pairs else None,
                               'matched_round_ratio_min': min(pairs) if pairs else None, 'matched_round_ratio_max': max(pairs) if pairs else None,
                               'ranges_overlap': max(a['min_logical_gibs'], b['min_logical_gibs']) <= min(a['max_logical_gibs'], b['max_logical_gibs']),
                               'effective_cpu_block_bytes_known': False,
                               'current_report_selected': a['current_report_selected'] and b['current_report_selected']})
    return winners, block_rows


def reference_drift(rows):
    groups = defaultdict(list)
    for row in rows:
        if row['role'] in ('reference-before', 'reference-after') and row['original_measurement_valid']:
            groups[(row['comparison_group'], row['configuration_id'])].append(row)
    output = []
    for (group, config), samples in sorted(groups.items(), key=lambda item: str(item[0])):
        samples.sort(key=lambda r: r['record_order'])
        first, last = samples[0], samples[-1]
        values = [r['throughput_logical_gibs'] for r in samples]
        middle = statistics.median(values)
        output.append({'study_id': first['study_id'], 'comparison_group': group, 'configuration_id': config,
                       'input_id': first['input_id'], 'backend': first['backend'], 'worker_threads': first['worker_threads'],
                       'sink': first['sink'], 'chunk_shape': first['chunk_shape'], 'codec': first['codec'],
                       'requested_duration_s': first['requested_duration_s'], 'observations': len(samples),
                       'first_run_id': first['row_id'], 'last_run_id': last['row_id'],
                       'first_gibs': values[0], 'last_gibs': values[-1],
                       'last_over_first': values[-1] / values[0], 'median_gibs': middle,
                       'min_gibs': min(values), 'max_gibs': max(values),
                       'observed_spread_percent': 100 * (max(values) - min(values)) / middle,
                       'current_report_selected': first['current_report_selected'],
                       'run_ids': [r['row_id'] for r in samples]})
    return output


def findings(rows, summaries, winners, blocks, drift):
    current = sorted((r for r in winners if r['current_report_selected'] and r['sink'] == 'fs'), key=lambda r: (r['input_id'], r['backend']))
    selected = [r for r in rows if r['current_report_selected'] and r['role'] == 'sample']
    selected_winners = [r for r in winners if r['current_report_selected']]
    selected_configs = [r for r in summaries if r['current_report_selected'] and r['role'] == 'sample']
    retry_rows = [r for r in rows if (r['recorded_attempt'] or 1) > 1]
    current_drift = [r for r in drift if r['current_report_selected'] and r['sink'] == 'fs']
    small_blocks = [r for r in blocks if r['current_report_selected'] and r['raw_chunk_bytes'] == 16384]
    block_case = {r['sink']: r for r in small_blocks if r['input_id'] == 'bbbc022-mito' and r['backend'] == 'gpu' and r['codec'] == 'blosc-lz4'}
    smallest_cycles = min(r['full_source_cycles'] for r in selected if r['full_source_cycles'] is not None)
    tail_ratio = max((r['source_cycle_tail_planes'] / r['logical_frames'] for r in selected if r['source_cycle_tail_planes']), default=0)
    text = [
        '# Streaming write findings', '',
        f'Exported {len(rows):,} recorded observations from {len(set(r["study_id"] for r in rows))} distinct microscopy/replay study families, including references, failures, calibration and fixed-layout controls. Public/path-sanitized copies were matched to original study executions and are listed as aliases in `write-metadata.json`; they add no observations. The dedicated shard-count study is covered by the separate concurrency export. Later writer-adapter campaigns are inventoried separately.', '',
        '**The archive does not establish a final stored-size optimum.** Its output counter is measured shard-write call bytes, not a final filesystem census. `strict_final_stored_size_winner` is null throughout. The separately labeled proxy follows the original analysis: sum measured shard-write bytes / sum logical input bytes, then choose greatest median logical GiB/s at no more than 1.10 times the smallest proxy value in a comparable group. The comparison uses exact integer fractions for the threshold and retains exact throughput ties.', '',
        f'The current report selects {len(selected_configs)} configurations and {len(selected)} sample observations from these exports. Its {len(selected_winners)} input/backend/sink conditions have {sum(16384 <= r["raw_chunk_bytes"] <= 65536 for r in selected_winners)} proxy winners in 16–64 KiB and {sum(r["raw_chunk_bytes"] > 65536 for r in selected_winners)} above 64 KiB. This does not support a universal 16–64 KiB write preference. CPU and GPU results are different resource budgets on different machines, and several GPU transfer inputs have only five selected settings. The main grids test 16, 64 and 256 KiB; DynaCell adds 128 KiB. They do not directly establish a 32 KiB write result.', '',
        '| Input | Backend / workers | Chunk / block request KiB | Codec | Logical GiB/s median [min,max] | Proxy extra bytes | Repeats |',
        '| --- | --- | --- | --- | --- | --- | --- |'
    ]
    for r in current:
        block = f'{r["blosc_block_requested_bytes"]/1024:g}' if r['blosc_block_requested_bytes'] else '—'
        text.append(f'| {r["input_id"]} | {r["backend"]} / {r["worker_threads"]} | {r["raw_chunk_bytes"]/1024:g} / {block} | {r["codec"]} | {r["median_logical_gibs"]:.3f} [{r["min_logical_gibs"]:.3f}, {r["max_logical_gibs"]:.3f}] | {r["proxy_size_penalty_percent"]:.2f}% | {r["valid_observations"]} |')
    text += ['', 'These are observed ranges, not confidence intervals. `write-winners.csv` identifies all eligible rivals with overlapping ranges and the best tested smaller/larger eligible alternative. Shape, codec, requested block, actual shard geometry and resources vary together in a whole-configuration choice; the winning chunk byte count is not a controlled chunk-only effect.', '',
             'Comparison groups preserve study/session, source hash and logical XY extent, dtype, replay depth/order, machine/backend, CPU allocation/worker count, sink/mount, output/I/O buffers, timing/minimum-work profile and memory budget. Earlier screens and later confirmations are never pooled. Corrected 32-worker Turin measurements replace the report view, not the retained earlier four-worker measurements. Repeated-plane-within-chunk observations are kept with an explicit exclusion. OpenCell depth-four worker controls remain separate from depth-one transfer studies.', '',
             'The normalization removes unequal replay volumes by reporting measured shard writes per logical GiB. These are repeated cyclic inputs, with a shared source hash within each group; raw file totals are never compared across different run lengths. XY padding and final chunk padding stay in the output cost. Per-row start plane, complete source cycles, tail planes, actual shape, submitted bytes and padded chunk bytes expose finite-cycle differences. This is a measured average cost over each replay, not an exact census for an identical finite array. The aggregate fold is a ratio of byte sums; it is neither the arithmetic mean nor median of per-run folds.', '',
             f'Normalization audit of the current view: {sum(bool(r["source_cycle_tail_planes"]) for r in selected)} of {len(selected)} samples end with a partial source cycle. All include at least {smallest_cycles:,} complete cycles; the largest tail is {100*tail_ratio:.4f}% of logical frames. These small fractions quantify the difference; they are not a bound on compressed-size error. No exact equal-finite-volume assumption is used for proxy eligibility. Current sample windows span {min(r["measurement_s"] for r in selected):.3f}–{max(r["measurement_s"] for r in selected):.3f} s including drain, with at least 32 GiB logical input.', '',
             'Source raw packs are fully loaded and XY-padded before the measured window. TIFF decoding and source I/O are not timed. Warmup is drained and excluded; measured elapsed time includes append, final drain, writer close/metadata publication and the filesystem queue flush. The counter excludes separately published metadata and counts write requests rather than durable storage. Record-level preparation, warmup, append, drain and process wall time are retained; they must not be interchanged.', '',
             'The native coverage rule requires pass/sufficient coverage, at least two warmup batches, four measured batches, two generation transitions, minimum timing and final drain no more than 10% of measured time. Per-study minimum logical work and timing are also checked. Reference drift is retained rather than used to discard points. The frontiers require complete studies and valid sample records; failed/partial studies and controls remain visible in `write-summary.csv`.', '',
             f'{len(retry_rows)} exported observation(s) report more than one internal native attempt. Earlier internal attempts are not separately retained by the native benchmark; their aggregate discarded duration is preserved, and no artificial per-attempt throughput is created. Warmup byte/time measurements stay on their owning observation because they are not separate measured samples.', '',
             'Host peak RSS is the Linux process lifetime high-water mark (RUSAGE_SELF), not complete TIFF conversion memory. Device used bytes are a free-memory delta, not a measured device peak; pinned and total estimates are modeled allocations. Source camera requirements are absent from the Pareto studies. Their coverage-qualified finite unpaced replay does not prove indefinite acquisition at a required rate. Controlled-arrival output-pool/recovery observations remain a separate family.', '',
             'The matched Blosc request comparisons are in `write-block-comparisons.csv`. GPU subdivision is modeled from the retained implementation as min(requested block, chunk); an encoded-header measurement is absent. CPU effective subdivision is unknown. Interpret the export as a requested-block intervention at fixed chunk/codec/shuffle/backend and geometry, not an automatically measured effective block size.', '',
             'NFSv3 nconnect=16 is retained only where a contemporaneous storage record supplies it; early NFS records without options remain unknown. L40 and Turin sample throughput must not be pooled. Two/three-round min–max ranges and bracket references show only the observed session. Matched rounds help compare block requests but do not remove between-session filesystem drift.', '',
             'Reproduce with `python3 write-analysis.py --worktree /path/to/archived/chucky --main /path/to/chucky --output .`. Portable regeneration from shipped observations requires no source checkout: `python3 write-analysis.py --from-rows write-runs.csv --metadata write-metadata.json --output regenerated`. No third-party packages, benchmarks or Slurm jobs are used.', '']
    if 'discard' in block_case and 'fs' in block_case:
        a, b = block_case['discard'], block_case['fs']
        text[-3:-3] = ['', f'Block counterexample: at the same 16 KiB chunk, BBBC022 GPU Blosc-LZ4 with bitshuffle changes from {a["smaller_request_median_gibs"]:.3f} to {a["larger_request_median_gibs"]:.3f} logical GiB/s on discard when the requested block increases from 4 to 16 KiB; observed ranges do not overlap. On NFS the corresponding medians are {b["smaller_request_median_gibs"]:.3f} and {b["larger_request_median_gibs"]:.3f}, with overlapping ranges. Thus a small block effect is not general; CPU discard 16 KiB comparisons are much closer and the filesystem can obscure the difference.', '']
    text[-3:-3] = ['Bracketing reference variation is exported in `write-reference-drift.csv`, using references separately from sample throughput. Current NFS first→last reference rates (logical GiB/s): ' + '; '.join(f'{r["input_id"]} {r["backend"]} {r["first_gibs"]:.3f}→{r["last_gibs"]:.3f}' for r in current_drift) + '. These do not establish network load as the cause; they demonstrate within-session variation that limits narrow ranking claims.', '']
    return '\n'.join(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worktree', type=Path, default=DEFAULT_WORKTREE)
    parser.add_argument('--main', type=Path, default=DEFAULT_MAIN)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--from-rows', type=Path)
    parser.add_argument('--metadata', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.from_rows:
        metadata_path = args.metadata or args.from_rows.parent / 'write-metadata.json'
        bundle = read_json(metadata_path)
        rows = read_csv(args.from_rows, bundle['row_schema'])
    else:
        rows, metadata, index = collect(args.worktree, args.main)
        bundle = {'version': 1, 'studies': metadata, 'report_index': index,
                  'definitions': {'logical_throughput': 'logical input / 2**30 / measured append-plus-final-drain seconds',
                                  'size_proxy': 'sum(measured shard-write bytes) / sum(logical input bytes)',
                                  'strict_final_stored_size_available': False,
                                  'null_csv': 'empty cells',
                                  'warmups': 'embedded byte/time windows, not separate invented observations',
                                  'gpu_block_model': 'min(requested, raw chunk bytes); implementation-derived, not encoded-header measurement',
                                  'host_peak': 'process lifetime RUSAGE_SELF ru_maxrss, excludes separate preprocessing processes',
                                  'device_used': 'free-memory difference, not peak',
                                  'partial_cycles': 'average byte cost across cyclic replay; source start/tail retained'}}
        bundle['row_schema'] = write_csv(args.output / 'write-runs.csv', rows)
        (args.output / 'write-metadata.json').write_text(json.dumps(bundle, indent=2) + '\n')
        inventory = [{k: v for k, v in m.items() if k in ('id', 'kind', 'status', 'disposition', 'created', 'finished', 'source_file', 'source_sha256', 'source_aliases', 'observations', 'exported_observations', 'report_selection')}
                     for m in metadata.values()]
        (args.output / 'write-source-manifest.json').write_text(json.dumps(inventory, indent=2) + '\n')
    if len({r['row_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate exported observation identities')
    summaries = summarize(rows)
    winners, blocks = comparisons(summaries, rows)
    write_csv(args.output / 'write-summary.csv', summaries)
    write_csv(args.output / 'write-frontier-data.csv', [r for r in summaries if r['proxy_frontier_eligible']])
    write_csv(args.output / 'write-winners.csv', winners)
    write_csv(args.output / 'write-block-comparisons.csv', blocks)
    drift = reference_drift(rows)
    write_csv(args.output / 'write-reference-drift.csv', drift)
    (args.output / 'write-findings.md').write_text(findings(rows, summaries, winners, blocks, drift))
    audit = {'rows': len(rows), 'unique_row_ids': len({r['row_id'] for r in rows}),
             'studies': len(set(r['study_id'] for r in rows)), 'summary_rows': len(summaries),
             'status_counts': dict(Counter(r['status'] for r in rows)),
             'role_counts': dict(Counter(r['role'] for r in rows)),
             'current_report_samples': sum(r['current_report_selected'] and r['role'] == 'sample' for r in rows),
             'current_report_configurations': sum(r['current_report_selected'] and r['role'] == 'sample' for r in summaries),
             'proxy_winners': len(winners), 'block_comparisons': len(blocks),
             'native_retry_observations': sum((r['recorded_attempt'] or 1) > 1 for r in rows),
             'source_file_bytes': sum(Path(p).stat().st_size for p in {r['source_file'] for r in rows}) if not args.from_rows else None}
    (args.output / 'write-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
