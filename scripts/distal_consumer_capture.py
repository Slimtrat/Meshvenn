"""Exact selected distal-chain Stytch capture lineage and isolated elbow proof."""
import math

from core.native_pose_probe import NativePoseProbe
from scripts.native_pose_coverage import local_motion
from scripts.shoulder_pose_derivation import document as probe_document

REVISION = '1503d4854c991335027255f79c42788954abcfbf'
SOURCE_BASE = 'godot/Stytch.GodotHost/Assets/Embodiment/Candidates/MeshVennDollDistalChainsV1/Evidence/Factory/'
ASSET_SHA = '58bb85ca53f4bc437b7eb62777ea2d25aeb84aee7b46c4a53f837a507f89849b'
INDEX_SHA256 = 'c6a753c04cab1818f420df283af833c9dc19e27251350cd3ab4cec8b83b5d000'
CASE_COUNT = 23
SCOPE = 'Exact nineteen selected-asset production snapshots and four visible isolated native-local elbow captures. Rotation excitation is not combined-pose, artistic or physical-contact acceptance.'
SOURCE_BLOBS = {
    'Elbows/meshvenn-elbow-left-45.pose.json': '85c526a10ac8889a71596a1b732e62cdb46f004e',
    'Elbows/meshvenn-elbow-left-90.pose.json': '96d3e9ec2632db8360ab71ee8aac4a7de5c2e4f6',
    'Elbows/meshvenn-elbow-right-45.pose.json': '774138d2366cf86602678241fd97d9764db5faf6',
    'Elbows/meshvenn-elbow-right-90.pose.json': '46a08a16db41455e60eb35d1ede1d55e7509973a',
    'Hop/meshvenn-hop-00.pose.json': '210871bbb560b2bf018fca2fc25b27273e7b6698',
    'Hop/meshvenn-hop-01.pose.json': '25912bc5de7ee42136ca2d0b8b16c21deebf6136',
    'Hop/meshvenn-hop-02.pose.json': '22bf83159a6840f653a4aa6ce2a614d32ef1a48f',
    'Hop/meshvenn-hop-03.pose.json': '1c14b25daeb8b02f57101eabeb30813e96a1e480',
    'Hop/meshvenn-hop-04.pose.json': '17d39a93d39353eab7b33c72da94bb8277cfb291',
    'Hop/meshvenn-hop-05.pose.json': '310f79e325d908cdc372e3e04d7ce31ec55a4d54',
    'Hop/meshvenn-hop-06.pose.json': 'fb6a75ad04bf8926d73c3db53493eb59d76abf1e',
    'Hop/meshvenn-hop-07.pose.json': '92ca4c97b8671e16209f3d5aa16c7fdbf93580cc',
    'Hop/meshvenn-hop-08.pose.json': 'c1296f39e9798aaaa8cf365a3fd7e9065393a11e',
    'Hop/meshvenn-hop-09.pose.json': 'fa518a87eaf38c9dc8b831e2403f1dc47aa488b8',
    'Hop/meshvenn-hop-10.pose.json': '221367c5086f031cc6842acabb656bf1aacf9d87',
    'Hop/meshvenn-hop-11.pose.json': 'e2869f9227710a8419565efac8717750b97d3b7c',
    'Walk/meshvenn-walk-00.pose.json': '0a96eca147bf6bcce6ce63099d1f2f8937955b9c',
    'Walk/meshvenn-walk-01.pose.json': '578572d0e9d0c75293b033cd7fd8d0f72d80ab01',
    'Walk/meshvenn-walk-02.pose.json': '91b92558cabeb56505b35aa20ac3b47e2ee991dc',
    'World/03-one-leg-hop.pose.json': 'b9ee0fe4eb67e021d3fd0a046c934f7cfc68e571',
    'factory-hall.pose.json': '7933a1c5f83f8b870471db6c85cbd4b6bec491e0',
    'factory-held.pose.json': 'f82ccbd389e3885f44e229d14b4c2d040c28bcc3',
    'factory-one-leg.pose.json': '4359737fe09859654b982b361e700bc18afad30f',
}
ELBOWS = {f'Elbows/meshvenn-elbow-{label}-{angle}.pose.json':(side,angle)
          for label,side in (('left','L'),('right','R')) for angle in (45,90)}


def elbow_excitation(name,raw,document,metadata):
    """Whitelist numeric excitation provenance only after checking actual deltas."""
    if name not in ELBOWS:return None
    side,requested=ELBOWS[name];context=raw['Context']
    if (type(context.get('Left')) is not bool or context['Left']!=(side=='L')
            or type(context.get('RequestedDegrees')) is not int or context['RequestedDegrees']!=requested
            or context.get('Visible') is not True
            or type(context.get('MeasuredRestRelativeDegrees')) not in (int,float)
            or not math.isfinite(context['MeasuredRestRelativeDegrees'])
            or any(role in metadata['hidden_regions'] for role in ('left-arm','right-arm'))):
        raise ValueError('Isolated elbow capture has contradictory side/angle/presence provenance.')
    bones={b.name:b for b in NativePoseProbe.from_dict(document).bones}
    name,opposite='forearm.'+side,'forearm.'+('R' if side=='L' else 'L')
    actual=local_motion(bones[name].rest,bones[name].pose)
    other=local_motion(bones[opposite].rest,bones[opposite].pose)
    if (not actual['rigid_delta'] or not other['rigid_delta']
            or abs(actual['rotation_degrees']-requested)>.05
            or abs(context['MeasuredRestRelativeDegrees']-actual['rotation_degrees'])>.05
            or other['rotation_degrees']>.05):
        raise ValueError('Isolated elbow matrices disagree with requested/measured rotation or opposite rest.')
    return {'joint':name,'requested_degrees':requested,'measured_degrees':round(actual['rotation_degrees'],6),
            'opposite_joint':opposite,'opposite_degrees':round(other['rotation_degrees'],6),
            'both_arms_visible':True,'scope':'Captured isolated native-local excitation, not combined-run acceptance.'}


def validate_projected_excitation(case,probe):
    """CI can recheck isolated labels using only already-public matrices."""
    path=case['source_path']
    name=path.removeprefix(SOURCE_BASE)
    if path!=SOURCE_BASE+name or name not in SOURCE_BLOBS or case['source_git_blob']!=SOURCE_BLOBS[name]:
        raise ValueError('Projected capture has different source Git lineage.')
    if name not in ELBOWS:
        if 'elbow_excitation' in case:raise ValueError('Production capture mislabeled as isolated elbow evidence.')
        return
    row=case.get('elbow_excitation')
    if not isinstance(row,dict):raise ValueError('Missing isolated elbow proof.')
    side,_=ELBOWS[name]
    raw={'Context':{'Left':side=='L','RequestedDegrees':row.get('requested_degrees'),
                    'MeasuredRestRelativeDegrees':row.get('measured_degrees'),
                    'Visible':row.get('both_arms_visible')}}
    actual=elbow_excitation(name,raw,probe_document(probe),{'hidden_regions':case['hidden_regions']})
    if row!=actual:raise ValueError('Projected isolated elbow proof differs from its actual matrices.')
