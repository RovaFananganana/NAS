# services/permission_audit_logger.py

import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from models.access_log import AccessLog
from extensions import db

class PermissionAuditLogger:
    """
    Service spécialisé pour l'audit et le logging des vérifications de permissions
    Fournit un logging détaillé pour diagnostiquer les problèmes de permissions
    """
    
    def __init__(self):
        self.log_levels = {
            'DEBUG': 0,
            'INFO': 1,
            'WARNING': 2,
            'ERROR': 3
        }
        self.current_level = self.log_levels['INFO']
    
    def set_log_level(self, level: str):
        """Définir le niveau de logging"""
        if level in self.log_levels:
            self.current_level = self.log_levels[level]
    
    def _should_log(self, level: str) -> bool:
        """Vérifier si on doit logger selon le niveau"""
        return self.log_levels.get(level, 0) >= self.current_level
    
    def _create_log_entry(self, user_id: int, action: str, target: str, 
                         level: str = 'INFO', details: Optional[Dict] = None,
                         performance_data: Optional[Dict] = None) -> None:
        """Créer une entrée de log dans la base de données"""
        try:
            # Construire les détails complets
            log_details = {
                'level': level,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'details': details or {},
                'performance': performance_data or {}
            }
            
            # Créer l'entrée de log
            # Note: AccessLog doesn't have a details field, so we include minimal details in target
            # Keep only essential info to avoid field size limit
            essential_details = {
                'level': level,
                'action': details.get('action', '') if details else ''
            }
            target_with_details = f"{target} | {json.dumps(essential_details)}"
            
            # Ensure we don't exceed field limit
            if len(target_with_details) > 250:
                target_with_details = target[:245] + "..."
            
            log_entry = AccessLog(
                user_id=user_id,
                action=action,
                target=target_with_details,
                timestamp=datetime.now(timezone.utc)
            )
            
            db.session.add(log_entry)
            # Note: Le commit sera fait par la fonction appelante
            
            # Log console pour debug
            if self._should_log('DEBUG'):
                print(f"🔍 [PERMISSION_AUDIT] {level}: User {user_id} - {action} - {target}")
                if details:
                    print(f"   Details: {json.dumps(details, indent=2, default=str)}")
                    
        except Exception as e:
            print(f"❌ Erreur lors de l'enregistrement du log d'audit: {str(e)}")
    
    def log_permission_check(self, user_id: int, path: str, result: Dict[str, Any], 
                           groups: List[Dict], timing: Dict[str, float]) -> None:
        """
        Logger une vérification de permissions avec tous les détails
        
        Args:
            user_id: ID de l'utilisateur
            path: Chemin vérifié
            result: Résultat de la vérification (permissions accordées)
            groups: Groupes de l'utilisateur et leurs permissions
            timing: Métriques de performance
        """
        if not self._should_log('INFO'):
            return
            
        details = {
            'path': path,
            'result': result,
            'user_groups': groups,
            'cache_hit': timing.get('cache_hit', False),
            'cache_age_ms': timing.get('cache_age_ms'),
            'queries_executed': timing.get('queries_executed', 0)
        }
        
        performance_data = {
            'total_duration_ms': timing.get('total_duration_ms', 0),
            'db_query_duration_ms': timing.get('db_query_duration_ms', 0),
            'cache_lookup_duration_ms': timing.get('cache_lookup_duration_ms', 0)
        }
        
        action = 'PERMISSION_CHECK'
        target = f"Path: {path}"
        
        self._create_log_entry(
            user_id=user_id,
            action=action,
            target=target,
            level='INFO',
            details=details,
            performance_data=performance_data
        )
    
    def log_permission_failure(self, user_id: int, path: str, error: str, 
                             context: Dict[str, Any]) -> None:
        """
        Logger un échec de vérification de permissions avec contexte complet
        
        Args:
            user_id: ID de l'utilisateur
            path: Chemin où l'échec s'est produit
            error: Message d'erreur
            context: Contexte supplémentaire (groupes, permissions attendues, etc.)
        """
        if not self._should_log('WARNING'):
            return
            
        details = {
            'path': path,
            'error_message': error,
            'context': context,
            'user_groups': context.get('user_groups', []),
            'expected_permissions': context.get('expected_permissions', {}),
            'actual_permissions': context.get('actual_permissions', {}),
            'cache_state': context.get('cache_state', {})
        }
        
        action = 'PERMISSION_FAILURE'
        target = f"Path: {path} - Error: {error}"
        
        self._create_log_entry(
            user_id=user_id,
            action=action,
            target=target,
            level='WARNING',
            details=details
        )
    
    def log_cache_operation(self, operation: str, user_id: int, path: str, 
                          result: Dict[str, Any]) -> None:
        """
        Logger les opérations de cache de permissions
        
        Args:
            operation: Type d'opération (HIT, MISS, SET, INVALIDATE, VALIDATE)
            user_id: ID de l'utilisateur
            path: Chemin concerné
            result: Résultat de l'opération
        """
        if not self._should_log('DEBUG'):
            return
            
        details = {
            'operation': operation,
            'path': path,
            'result': result,
            'cache_size': result.get('cache_size'),
            'cache_age_ms': result.get('cache_age_ms'),
            'hit_rate': result.get('hit_rate')
        }
        
        action = f'CACHE_{operation}'
        target = f"Path: {path}"
        
        self._create_log_entry(
            user_id=user_id,
            action=action,
            target=target,
            level='DEBUG',
            details=details
        )
    
    def log_permission_inconsistency(self, user_id: int, path: str, 
                                   inconsistency_data: Dict[str, Any]) -> None:
        """
        Logger les incohérences de permissions détectées
        
        Args:
            user_id: ID de l'utilisateur
            path: Chemin où l'incohérence est détectée
            inconsistency_data: Données sur l'incohérence
        """
        if not self._should_log('ERROR'):
            return
            
        details = {
            'path': path,
            'inconsistency_type': inconsistency_data.get('type'),
            'cached_permissions': inconsistency_data.get('cached_permissions'),
            'fresh_permissions': inconsistency_data.get('fresh_permissions'),
            'differences': inconsistency_data.get('differences', []),
            'cache_age_ms': inconsistency_data.get('cache_age_ms'),
            'resolution_action': inconsistency_data.get('resolution_action')
        }
        
        action = 'PERMISSION_INCONSISTENCY'
        target = f"Path: {path} - Type: {inconsistency_data.get('type', 'unknown')}"
        
        self._create_log_entry(
            user_id=user_id,
            action=action,
            target=target,
            level='ERROR',
            details=details
        )
    
    def log_performance_metrics(self, user_id: int, operation: str, 
                              metrics: Dict[str, Any]) -> None:
        """
        Logger les métriques de performance des opérations de permissions
        
        Args:
            user_id: ID de l'utilisateur
            operation: Type d'opération
            metrics: Métriques de performance
        """
        if not self._should_log('INFO'):
            return
            
        details = {
            'operation': operation,
            'metrics': metrics
        }
        
        performance_data = {
            'total_duration_ms': metrics.get('total_duration_ms', 0),
            'db_queries': metrics.get('db_queries', 0),
            'cache_operations': metrics.get('cache_operations', 0),
            'memory_usage_mb': metrics.get('memory_usage_mb', 0)
        }
        
        action = 'PERFORMANCE_METRICS'
        target = f"Operation: {operation}"
        
        self._create_log_entry(
            user_id=user_id,
            action=action,
            target=target,
            level='INFO',
            details=details,
            performance_data=performance_data
        )
    
    def log_file_operation(self, user_id: int, operation: str, path: str, 
                          details: Optional[Dict[str, Any]] = None,
                          timing: Optional[Dict[str, float]] = None) -> None:
        """
        Logger les opérations sur les fichiers et dossiers
        
        Args:
            user_id: ID de l'utilisateur
            operation: Type d'opération (READ, WRITE, DELETE, COPY, MOVE, DOWNLOAD, etc.)
            path: Chemin du fichier/dossier
            details: Détails supplémentaires de l'opération
            timing: Métriques de performance
        """
        if not self._should_log('INFO'):
            return
            
        log_details = {
            'path': path,
            'operation': operation,
            'details': details or {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        performance_data = timing or {}
        
        action = f'FILE_{operation.upper()}'
        target = f"Path: {path}"
        
        self._create_log_entry(
            user_id=user_id,
            action=action,
            target=target,
            level='INFO',
            details=log_details,
            performance_data=performance_data
        )
    
    def log_folder_operation(self, user_id: int, operation: str, path: str,
                           details: Optional[Dict[str, Any]] = None,
                           timing: Optional[Dict[str, float]] = None) -> None:
        """
        Logger les opérations sur les dossiers
        
        Args:
            user_id: ID de l'utilisateur
            operation: Type d'opération (OPEN, CREATE, DELETE, COPY, MOVE, etc.)
            path: Chemin du dossier
            details: Détails supplémentaires de l'opération
            timing: Métriques de performance
        """
        if not self._should_log('INFO'):
            return
            
        log_details = {
            'path': path,
            'operation': operation,
            'details': details or {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        performance_data = timing or {}
        
        action = f'FOLDER_{operation.upper()}'
        target = f"Path: {path}"
        
        self._create_log_entry(
            user_id=user_id,
            action=action,
            target=target,
            level='INFO',
            details=log_details,
            performance_data=performance_data
        )
    
    def log_download_operation(self, user_id: int, file_path: str, 
                             file_size: Optional[int] = None,
                             timing: Optional[Dict[str, float]] = None) -> None:
        """
        Logger spécifiquement les téléchargements de fichiers
        
        Args:
            user_id: ID de l'utilisateur
            file_path: Chemin du fichier téléchargé
            file_size: Taille du fichier en bytes
            timing: Métriques de performance
        """
        details = {
            'file_path': file_path,
            'file_size_bytes': file_size,
            'file_size_human': self._format_file_size(file_size) if file_size else None
        }
        
        self.log_file_operation(
            user_id=user_id,
            operation='DOWNLOAD',
            path=file_path,
            details=details,
            timing=timing
        )
    
    def log_upload_operation(self, user_id: int, file_path: str, 
                           file_size: Optional[int] = None,
                           overwrite: bool = False,
                           timing: Optional[Dict[str, float]] = None) -> None:
        """
        Logger spécifiquement les uploads de fichiers
        
        Args:
            user_id: ID de l'utilisateur
            file_path: Chemin du fichier uploadé
            file_size: Taille du fichier en bytes
            overwrite: Si le fichier a été écrasé
            timing: Métriques de performance
        """
        details = {
            'file_path': file_path,
            'file_size_bytes': file_size,
            'file_size_human': self._format_file_size(file_size) if file_size else None,
            'overwrite': overwrite
        }
        
        self.log_file_operation(
            user_id=user_id,
            operation='UPLOAD',
            path=file_path,
            details=details,
            timing=timing
        )
    
    def log_copy_operation(self, user_id: int, source_path: str, dest_path: str,
                         is_folder: bool = False,
                         timing: Optional[Dict[str, float]] = None) -> None:
        """
        Logger les opérations de copie
        
        Args:
            user_id: ID de l'utilisateur
            source_path: Chemin source
            dest_path: Chemin de destination
            is_folder: True si c'est un dossier
            timing: Métriques de performance
        """
        details = {
            'source_path': source_path,
            'destination_path': dest_path,
            'is_folder': is_folder
        }
        
        if is_folder:
            self.log_folder_operation(
                user_id=user_id,
                operation='COPY',
                path=source_path,
                details=details,
                timing=timing
            )
        else:
            self.log_file_operation(
                user_id=user_id,
                operation='COPY',
                path=source_path,
                details=details,
                timing=timing
            )
    
    def log_move_operation(self, user_id: int, source_path: str, dest_path: str,
                         is_folder: bool = False,
                         timing: Optional[Dict[str, float]] = None) -> None:
        """
        Logger les opérations de déplacement
        
        Args:
            user_id: ID de l'utilisateur
            source_path: Chemin source
            dest_path: Chemin de destination
            is_folder: True si c'est un dossier
            timing: Métriques de performance
        """
        details = {
            'source_path': source_path,
            'destination_path': dest_path,
            'is_folder': is_folder
        }
        
        if is_folder:
            self.log_folder_operation(
                user_id=user_id,
                operation='MOVE',
                path=source_path,
                details=details,
                timing=timing
            )
        else:
            self.log_file_operation(
                user_id=user_id,
                operation='MOVE',
                path=source_path,
                details=details,
                timing=timing
            )
    
    def log_delete_operation(self, user_id: int, path: str, is_folder: bool = False,
                           timing: Optional[Dict[str, float]] = None) -> None:
        """
        Logger les opérations de suppression
        
        Args:
            user_id: ID de l'utilisateur
            path: Chemin de l'élément supprimé
            is_folder: True si c'est un dossier
            timing: Métriques de performance
        """
        details = {
            'path': path,
            'is_folder': is_folder
        }
        
        if is_folder:
            self.log_folder_operation(
                user_id=user_id,
                operation='DELETE',
                path=path,
                details=details,
                timing=timing
            )
        else:
            self.log_file_operation(
                user_id=user_id,
                operation='DELETE',
                path=path,
                details=details,
                timing=timing
            )
    
    def log_read_operation(self, user_id: int, file_path: str,
                         timing: Optional[Dict[str, float]] = None) -> None:
        """
        Logger les opérations de lecture de fichiers
        
        Args:
            user_id: ID de l'utilisateur
            file_path: Chemin du fichier lu
            timing: Métriques de performance
        """
        self.log_file_operation(
            user_id=user_id,
            operation='READ',
            path=file_path,
            timing=timing
        )
    
    def log_folder_open_operation(self, user_id: int, folder_path: str,
                                timing: Optional[Dict[str, float]] = None) -> None:
        """
        Logger les opérations d'ouverture de dossiers
        
        Args:
            user_id: ID de l'utilisateur
            folder_path: Chemin du dossier ouvert
            timing: Métriques de performance
        """
        self.log_folder_operation(
            user_id=user_id,
            operation='OPEN',
            path=folder_path,
            timing=timing
        )
    
    def _format_file_size(self, bytes_size: int) -> str:
        """Formater la taille de fichier en format lisible"""
        if not bytes_size:
            return '0 B'
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"
    
    def get_audit_trail(self, user_id: Optional[int] = None, path: Optional[str] = None, 
                       action_filter: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Récupérer l'historique d'audit des permissions
        
        Args:
            user_id: Filtrer par utilisateur (optionnel)
            path: Filtrer par chemin (optionnel)
            action_filter: Filtrer par type d'action (optionnel)
            limit: Nombre maximum d'entrées à retourner
            
        Returns:
            Liste des entrées d'audit
        """
        try:
            query = AccessLog.query
            
            # Filtrer par utilisateur
            if user_id:
                query = query.filter(AccessLog.user_id == user_id)
            
            # Filtrer par chemin (dans le target)
            if path:
                query = query.filter(AccessLog.target.contains(f"Path: {path}"))
            
            # Filtrer par action
            if action_filter:
                query = query.filter(AccessLog.action.contains(action_filter))
            
            # Ordonner par timestamp décroissant et limiter
            logs = query.order_by(AccessLog.timestamp.desc()).limit(limit).all()
            
            # Convertir en dictionnaires
            audit_trail = []
            for log in logs:
                entry = {
                    'id': log.id,
                    'user_id': log.user_id,
                    'action': log.action,
                    'target': log.target,
                    'timestamp': log.timestamp.isoformat(),
                    'details': {}
                }
                
                # Parser les détails JSON si disponibles
                if log.details:
                    try:
                        entry['details'] = json.loads(log.details)
                    except json.JSONDecodeError:
                        entry['details'] = {'raw': log.details}
                
                audit_trail.append(entry)
            
            return audit_trail
            
        except Exception as e:
            print(f"❌ Erreur lors de la récupération de l'audit trail: {str(e)}")
            return []
    
    def get_performance_summary(self, user_id: Optional[int] = None, 
                              hours: int = 24) -> Dict[str, Any]:
        """
        Obtenir un résumé des performances des permissions
        
        Args:
            user_id: Filtrer par utilisateur (optionnel)
            hours: Période en heures à analyser
            
        Returns:
            Résumé des performances
        """
        try:
            from datetime import timedelta
            
            # Calculer la date de début
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            query = AccessLog.query.filter(AccessLog.timestamp >= start_time)
            
            if user_id:
                query = query.filter(AccessLog.user_id == user_id)
            
            # Filtrer les actions de permissions
            permission_actions = [
                'PERMISSION_CHECK', 'PERMISSION_FAILURE', 
                'CACHE_HIT', 'CACHE_MISS', 'PERFORMANCE_METRICS'
            ]
            
            logs = query.filter(AccessLog.action.in_(permission_actions)).all()
            
            # Analyser les performances
            total_checks = 0
            total_failures = 0
            cache_hits = 0
            cache_misses = 0
            total_duration = 0
            durations = []
            
            for log in logs:
                if log.action == 'PERMISSION_CHECK':
                    total_checks += 1
                    # Extraire la durée si disponible
                    if log.details:
                        try:
                            details = json.loads(log.details)
                            duration = details.get('performance', {}).get('total_duration_ms', 0)
                            if duration > 0:
                                total_duration += duration
                                durations.append(duration)
                        except json.JSONDecodeError:
                            pass
                            
                elif log.action == 'PERMISSION_FAILURE':
                    total_failures += 1
                elif log.action == 'CACHE_HIT':
                    cache_hits += 1
                elif log.action == 'CACHE_MISS':
                    cache_misses += 1
            
            # Calculer les statistiques
            avg_duration = total_duration / len(durations) if durations else 0
            cache_hit_rate = cache_hits / (cache_hits + cache_misses) if (cache_hits + cache_misses) > 0 else 0
            failure_rate = total_failures / total_checks if total_checks > 0 else 0
            
            return {
                'period_hours': hours,
                'total_permission_checks': total_checks,
                'total_failures': total_failures,
                'failure_rate': failure_rate,
                'cache_hits': cache_hits,
                'cache_misses': cache_misses,
                'cache_hit_rate': cache_hit_rate,
                'average_duration_ms': avg_duration,
                'min_duration_ms': min(durations) if durations else 0,
                'max_duration_ms': max(durations) if durations else 0,
                'total_logs_analyzed': len(logs)
            }
            
        except Exception as e:
            print(f"❌ Erreur lors du calcul du résumé de performance: {str(e)}")
            return {
                'error': str(e),
                'period_hours': hours,
                'total_permission_checks': 0
            }

# Instance globale du logger
permission_audit_logger = PermissionAuditLogger()