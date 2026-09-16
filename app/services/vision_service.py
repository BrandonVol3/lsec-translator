"""
Módulo 3 — Servicio de Visión Artificial y Mapeo Gestual.

Utiliza MediaPipe Holistic para extraer puntos de referencia 3D
normalizados (manos, pose corporal, rostro) y los estructura en
un formato compatible con redes ST-GCN y motores gráficos 3D.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

from app.core.schemas import (
    BlendshapeValue,
    FaceKeypoints,
    HandKeypoints,
    KeypointsFrame,
    Landmark3D,
    PoseKeypoints,
)

logger = logging.getLogger(__name__)


class SpatialGestureService:
    """
    Servicio de extracción y mapeo de puntos clave espaciales.

    Utiliza MediaPipe Holistic para extraer los 543 landmarks
    normalizados por frame y los convierte a formatos compatibles
    con motores gráficos (UE5) y redes ST-GCN.
    """

    # Conteos de landmarks de MediaPipe Holistic
    FACE_LANDMARKS_COUNT = 468
    POSE_LANDMARKS_COUNT = 33
    HAND_LANDMARKS_COUNT = 21

    def __init__(
        self,
        static_image_mode: bool = False,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self._static_image_mode = static_image_mode
        self._model_complexity = model_complexity
        self._min_detection_confidence = min_detection_confidence
        self._min_tracking_confidence = min_tracking_confidence
        self._holistic = None
        logger.info(
            "SpatialGestureService configurado: complexity=%d, det_conf=%.2f, track_conf=%.2f",
            model_complexity,
            min_detection_confidence,
            min_tracking_confidence,
        )

    def _init_holistic(self) -> None:
        """Inicializa MediaPipe Holistic de forma lazy."""
        if self._holistic is not None:
            return

        try:
            import mediapipe as mp

            self._mp_holistic = mp.solutions.holistic
            self._holistic = self._mp_holistic.Holistic(
                static_image_mode=self._static_image_mode,
                model_complexity=self._model_complexity,
                min_detection_confidence=self._min_detection_confidence,
                min_tracking_confidence=self._min_tracking_confidence,
            )
            logger.info("MediaPipe Holistic inicializado correctamente.")
        except ImportError:
            logger.error("mediapipe no está instalado. Ejecute: pip install mediapipe")
            raise
        except Exception as exc:
            logger.error("Error inicializando MediaPipe: %s", exc)
            raise RuntimeError(f"No se pudo inicializar MediaPipe Holistic: {exc}") from exc

    def _landmarks_to_list(
        self,
        landmarks,
        count: int,
    ) -> List[Landmark3D]:
        """Convierte landmarks de MediaPipe a lista de Landmark3D."""
        result: list[Landmark3D] = []
        if landmarks is None:
            # Retornar landmarks vacíos (ceros) si no se detectaron
            return [Landmark3D(x=0.0, y=0.0, z=0.0, visibility=0.0) for _ in range(count)]

        for lm in landmarks.landmark:
            result.append(
                Landmark3D(
                    x=round(lm.x, 6),
                    y=round(lm.y, 6),
                    z=round(lm.z, 6),
                    visibility=round(getattr(lm, "visibility", 1.0), 4),
                )
            )

        # Rellenar si faltan landmarks
        while len(result) < count:
            result.append(Landmark3D(x=0.0, y=0.0, z=0.0, visibility=0.0))

        return result[:count]

    def extract_keypoints(
        self,
        frame: np.ndarray,
        frame_index: int = 0,
        timestamp_ms: float = 0.0,
    ) -> KeypointsFrame:
        """
        Procesa un frame BGR y extrae todos los landmarks normalizados.

        Args:
            frame: Imagen en formato BGR (numpy array, shape HxWx3).
            frame_index: Índice del frame en la secuencia.
            timestamp_ms: Timestamp del frame en milisegundos.

        Returns:
            KeypointsFrame con landmarks de manos, pose y rostro.

        Raises:
            ValueError: Si el frame es inválido.
            RuntimeError: Si falla la extracción de landmarks.
        """
        import cv2

        if frame is None or frame.size == 0:
            raise ValueError("Frame vacío o inválido.")

        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(
                f"Frame debe ser HxWx3 BGR, recibido: {frame.shape}"
            )

        self._init_holistic()

        try:
            # MediaPipe requiere RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._holistic.process(rgb_frame)

            # Extraer landmarks de cada componente
            left_hand = None
            right_hand = None
            pose = None
            face = None

            if results.left_hand_landmarks:
                left_hand = HandKeypoints(
                    landmarks=self._landmarks_to_list(
                        results.left_hand_landmarks, self.HAND_LANDMARKS_COUNT
                    ),
                    handedness="left",
                    confidence=self._min_detection_confidence,
                )

            if results.right_hand_landmarks:
                right_hand = HandKeypoints(
                    landmarks=self._landmarks_to_list(
                        results.right_hand_landmarks, self.HAND_LANDMARKS_COUNT
                    ),
                    handedness="right",
                    confidence=self._min_detection_confidence,
                )

            if results.pose_landmarks:
                pose = PoseKeypoints(
                    landmarks=self._landmarks_to_list(
                        results.pose_landmarks, self.POSE_LANDMARKS_COUNT
                    ),
                    confidence=self._min_detection_confidence,
                )

            if results.face_landmarks:
                face = FaceKeypoints(
                    landmarks=self._landmarks_to_list(
                        results.face_landmarks, self.FACE_LANDMARKS_COUNT
                    ),
                    confidence=self._min_detection_confidence,
                )

            return KeypointsFrame(
                frame_index=frame_index,
                timestamp_ms=timestamp_ms,
                left_hand=left_hand,
                right_hand=right_hand,
                pose=pose,
                face=face,
            )

        except ValueError:
            raise
        except Exception as exc:
            logger.error("Error extrayendo keypoints del frame %d: %s", frame_index, exc)
            raise RuntimeError(f"Error en extracción de keypoints: {exc}") from exc

    def process_video(
        self,
        video_path: str | Path,
        max_frames: Optional[int] = None,
    ) -> List[KeypointsFrame]:
        """
        Extrae keypoints de todos los frames de un archivo de video.

        Args:
            video_path: Ruta al archivo de video.
            max_frames: Límite máximo de frames a procesar (None = todos).

        Returns:
            Lista de KeypointsFrame, uno por cada frame procesado.

        Raises:
            FileNotFoundError: Si el archivo no existe.
            RuntimeError: Si no se puede abrir el video.
        """
        import cv2

        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video no encontrado: {video_path}")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"No se pudo abrir el video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames: list[KeypointsFrame] = []
        frame_idx = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if max_frames is not None and frame_idx >= max_frames:
                    break

                timestamp_ms = (frame_idx / fps) * 1000.0
                keypoints = self.extract_keypoints(
                    frame,
                    frame_index=frame_idx,
                    timestamp_ms=timestamp_ms,
                )
                frames.append(keypoints)
                frame_idx += 1

                if frame_idx % 100 == 0:
                    logger.info("Procesados %d frames...", frame_idx)

        finally:
            cap.release()

        logger.info("Video procesado: %d frames extraídos.", len(frames))
        return frames

    def format_for_stgcn(
        self,
        frames: List[KeypointsFrame],
        include_face: bool = False,
    ) -> np.ndarray:
        """
        Convierte una secuencia de KeypointsFrame a formato ST-GCN.

        Formato de salida: (N, C, T, V, M)
        - N: número de muestras (1 para una secuencia)
        - C: número de canales (3: x, y, z)
        - T: número de frames temporales
        - V: número de vértices/nodos del grafo
        - M: número de personas (1)

        Args:
            frames: Lista de KeypointsFrame.
            include_face: Si True, incluye landmarks faciales (468 extra).

        Returns:
            np.ndarray con forma (1, 3, T, V, 1).
        """
        if not frames:
            return np.zeros((1, 3, 0, 0, 1), dtype=np.float32)

        # Calcular V: pose(33) + mano_izq(21) + mano_der(21) + [face(468)]
        v = self.POSE_LANDMARKS_COUNT + 2 * self.HAND_LANDMARKS_COUNT
        if include_face:
            v += self.FACE_LANDMARKS_COUNT

        t = len(frames)
        data = np.zeros((1, 3, t, v, 1), dtype=np.float32)

        for frame_idx, frame in enumerate(frames):
            offset = 0

            # Pose landmarks
            if frame.pose:
                for j, lm in enumerate(frame.pose.landmarks):
                    data[0, 0, frame_idx, offset + j, 0] = lm.x
                    data[0, 1, frame_idx, offset + j, 0] = lm.y
                    data[0, 2, frame_idx, offset + j, 0] = lm.z
            offset += self.POSE_LANDMARKS_COUNT

            # Mano izquierda
            if frame.left_hand:
                for j, lm in enumerate(frame.left_hand.landmarks):
                    data[0, 0, frame_idx, offset + j, 0] = lm.x
                    data[0, 1, frame_idx, offset + j, 0] = lm.y
                    data[0, 2, frame_idx, offset + j, 0] = lm.z
            offset += self.HAND_LANDMARKS_COUNT

            # Mano derecha
            if frame.right_hand:
                for j, lm in enumerate(frame.right_hand.landmarks):
                    data[0, 0, frame_idx, offset + j, 0] = lm.x
                    data[0, 1, frame_idx, offset + j, 0] = lm.y
                    data[0, 2, frame_idx, offset + j, 0] = lm.z
            offset += self.HAND_LANDMARKS_COUNT

            # Rostro (opcional)
            if include_face and frame.face:
                for j, lm in enumerate(frame.face.landmarks):
                    data[0, 0, frame_idx, offset + j, 0] = lm.x
                    data[0, 1, frame_idx, offset + j, 0] = lm.y
                    data[0, 2, frame_idx, offset + j, 0] = lm.z

        logger.info(
            "Tensor ST-GCN generado: forma=%s, dtype=%s",
            data.shape,
            data.dtype,
        )
        return data

    def close(self) -> None:
        """Libera los recursos de MediaPipe."""
        if self._holistic is not None:
            self._holistic.close()
            self._holistic = None
            logger.info("MediaPipe Holistic cerrado.")
